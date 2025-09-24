"""
Performance optimization module with caching, async I/O, and resilience patterns.
Provides high-performance capabilities for the production RAG system.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Redis imports with fallback
try:
    import redis
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Async database support
try:
    import asyncpg
    import aiooracledb
    ASYNC_DB_AVAILABLE = True
except ImportError:
    ASYNC_DB_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int = 0
    last_accessed: datetime = None


class InMemoryCache:
    """
    High-performance in-memory cache with TTL and LRU eviction.
    """
    
    def __init__(self, max_size: int = 10000, default_ttl: int = 3600):
        """
        Initialize in-memory cache.
        
        Args:
            max_size: Maximum number of entries
            default_ttl: Default time-to-live in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        
        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _generate_key(self, key_parts: List[str]) -> str:
        """Generate cache key from parts."""
        key_string = "|".join(str(part) for part in key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        with self._lock:
            entry = self.cache.get(key)
            
            if entry is None:
                return None
            
            # Check expiration
            if entry.expires_at and datetime.utcnow() > entry.expires_at:
                del self.cache[key]
                return None
            
            # Update access info
            entry.access_count += 1
            entry.last_accessed = datetime.utcnow()
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache."""
        with self._lock:
            ttl = ttl or self.default_ttl
            expires_at = datetime.utcnow() + timedelta(seconds=ttl) if ttl > 0 else None
            
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
                last_accessed=datetime.utcnow()
            )
            
            self.cache[key] = entry
            
            # Evict if over size limit
            if len(self.cache) > self.max_size:
                self._evict_lru()
    
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        with self._lock:
            return self.cache.pop(key, None) is not None
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self.cache.clear()
    
    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self.cache:
            return
        
        # Find LRU entry
        lru_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k].last_accessed or datetime.min
        )
        
        del self.cache[lru_key]
    
    def _cleanup_loop(self) -> None:
        """Background cleanup of expired entries."""
        while True:
            try:
                time.sleep(300)  # Check every 5 minutes
                self._cleanup_expired()
            except Exception as e:
                logger.warning(f"Cache cleanup error: {e}")
    
    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        with self._lock:
            now = datetime.utcnow()
            expired_keys = [
                key for key, entry in self.cache.items()
                if entry.expires_at and now > entry.expires_at
            ]
            
            for key in expired_keys:
                del self.cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = datetime.utcnow()
            total_entries = len(self.cache)
            expired_count = sum(
                1 for entry in self.cache.values()
                if entry.expires_at and now > entry.expires_at
            )
            
            return {
                "total_entries": total_entries,
                "max_size": self.max_size,
                "expired_count": expired_count,
                "memory_efficiency": (total_entries - expired_count) / max(total_entries, 1)
            }


class RedisCache:
    """
    Redis-based distributed cache for multi-instance deployments.
    """
    
    def __init__(self, 
                 redis_url: str = "redis://localhost:6379",
                 key_prefix: str = "pio_ai:",
                 default_ttl: int = 3600):
        """
        Initialize Redis cache.
        
        Args:
            redis_url: Redis connection URL
            key_prefix: Prefix for all cache keys
            default_ttl: Default time-to-live in seconds
        """
        if not REDIS_AVAILABLE:
            raise ImportError("Redis is not available. Install redis-py package.")
        
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        
        # Sync client
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        
        # Test connection
        try:
            self.redis_client.ping()
            logger.info("Redis cache connected successfully")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            raise
    
    def _make_key(self, key: str) -> str:
        """Create prefixed cache key."""
        return f"{self.key_prefix}{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        try:
            cache_key = self._make_key(key)
            data = self.redis_client.get(cache_key)
            
            if data is None:
                return None
            
            # Deserialize JSON
            return json.loads(data)
            
        except Exception as e:
            logger.warning(f"Redis get error for key {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in Redis cache."""
        try:
            cache_key = self._make_key(key)
            ttl = ttl or self.default_ttl
            
            # Serialize to JSON
            data = json.dumps(value, default=str, ensure_ascii=False)
            
            # Set with TTL
            return self.redis_client.setex(cache_key, ttl, data)
            
        except Exception as e:
            logger.warning(f"Redis set error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from Redis cache."""
        try:
            cache_key = self._make_key(key)
            return bool(self.redis_client.delete(cache_key))
        except Exception as e:
            logger.warning(f"Redis delete error for key {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Clear keys matching pattern."""
        try:
            cache_pattern = self._make_key(pattern)
            keys = self.redis_client.keys(cache_pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Redis clear pattern error: {e}")
            return 0


class CacheManager:
    """
    Unified cache manager supporting multiple backends.
    """
    
    def __init__(self, 
                 use_redis: bool = False,
                 redis_url: str = None,
                 memory_cache_size: int = 10000,
                 default_ttl: int = 3600):
        """
        Initialize cache manager.
        
        Args:
            use_redis: Whether to use Redis as primary cache
            redis_url: Redis connection URL
            memory_cache_size: Size of in-memory cache
            default_ttl: Default TTL for cache entries
        """
        self.default_ttl = default_ttl
        
        # Always have in-memory cache for L1
        self.memory_cache = InMemoryCache(memory_cache_size, default_ttl)
        
        # Optional Redis cache for L2
        self.redis_cache = None
        if use_redis and REDIS_AVAILABLE and redis_url:
            try:
                self.redis_cache = RedisCache(redis_url, default_ttl=default_ttl)
                logger.info("Multi-level caching enabled (Memory + Redis)")
            except Exception as e:
                logger.warning(f"Redis cache initialization failed: {e}")
        
        if not self.redis_cache:
            logger.info("Single-level caching enabled (Memory only)")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value with L1/L2 cache hierarchy."""
        # Try L1 (memory) first
        value = self.memory_cache.get(key)
        if value is not None:
            return value
        
        # Try L2 (Redis) if available
        if self.redis_cache:
            value = self.redis_cache.get(key)
            if value is not None:
                # Populate L1 cache
                self.memory_cache.set(key, value, ttl=self.default_ttl // 2)
                return value
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in both cache levels."""
        ttl = ttl or self.default_ttl
        
        # Set in L1
        self.memory_cache.set(key, value, ttl)
        
        # Set in L2 if available
        if self.redis_cache:
            self.redis_cache.set(key, value, ttl)
    
    def delete(self, key: str) -> None:
        """Delete key from both cache levels."""
        self.memory_cache.delete(key)
        if self.redis_cache:
            self.redis_cache.delete(key)
    
    def clear_pattern(self, pattern: str) -> None:
        """Clear keys matching pattern."""
        # For memory cache, we need to implement pattern matching
        if "*" in pattern:
            pattern_prefix = pattern.replace("*", "")
            with self.memory_cache._lock:
                keys_to_delete = [
                    key for key in self.memory_cache.cache.keys()
                    if key.startswith(pattern_prefix)
                ]
                for key in keys_to_delete:
                    del self.memory_cache.cache[key]
        
        # Redis supports pattern clearing natively
        if self.redis_cache:
            self.redis_cache.clear_pattern(pattern)


def cached(cache_manager: CacheManager, 
          ttl: Optional[int] = None,
          key_parts: Optional[List[str]] = None):
    """
    Decorator for caching function results.
    
    Args:
        cache_manager: Cache manager instance
        ttl: Time-to-live for cached result
        key_parts: List of argument names to include in cache key
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_parts:
                key_values = []
                for i, part in enumerate(key_parts):
                    if i < len(args):
                        key_values.append(str(args[i]))
                    elif part in kwargs:
                        key_values.append(str(kwargs[part]))
                    else:
                        key_values.append("none")
            else:
                # Use all arguments
                key_values = [str(arg) for arg in args] + [f"{k}:{v}" for k, v in sorted(kwargs.items())]
            
            cache_key = f"{func.__name__}:" + hashlib.md5(
                "|".join(key_values).encode()
            ).hexdigest()
            
            # Try cache first
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            cache_manager.set(cache_key, result, ttl)
            
            return result
        
        # Add cache control methods
        wrapper.cache_clear = lambda pattern="*": cache_manager.clear_pattern(f"{func.__name__}:{pattern}")
        wrapper.cache_delete = lambda *args, **kwargs: cache_manager.delete(
            f"{func.__name__}:" + hashlib.md5(
                "|".join([str(arg) for arg in args] + [f"{k}:{v}" for k, v in sorted(kwargs.items())]
            ).encode()).hexdigest()
        )
        
        return wrapper
    
    return decorator


class AsyncDatabasePool:
    """
    Async database connection pool for high-performance database operations.
    """
    
    def __init__(self, 
                 db_type: str,
                 connection_string: str,
                 pool_size: int = 20,
                 max_overflow: int = 10):
        """
        Initialize async database pool.
        
        Args:
            db_type: Database type ('postgres' or 'oracle')
            connection_string: Database connection string
            pool_size: Base pool size
            max_overflow: Maximum overflow connections
        """
        if not ASYNC_DB_AVAILABLE:
            raise ImportError("Async database support not available")
        
        self.db_type = db_type.lower()
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool = None
    
    async def initialize(self):
        """Initialize the connection pool."""
        try:
            if self.db_type == 'postgres':
                self.pool = await asyncpg.create_pool(
                    self.connection_string,
                    min_size=self.pool_size,
                    max_size=self.pool_size + self.max_overflow
                )
            elif self.db_type == 'oracle':
                # Oracle async pool setup (simplified)
                self.pool = await aiooracledb.create_pool(
                    dsn=self.connection_string,
                    min=self.pool_size,
                    max=self.pool_size + self.max_overflow
                )
            else:
                raise ValueError(f"Unsupported database type: {self.db_type}")
            
            logger.info(f"Async {self.db_type} pool initialized with {self.pool_size} connections")
            
        except Exception as e:
            logger.error(f"Failed to initialize async database pool: {e}")
            raise
    
    async def execute_query(self, query: str, params: Optional[List] = None) -> List[Dict]:
        """Execute query and return results."""
        if not self.pool:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                if self.db_type == 'postgres':
                    if params:
                        rows = await conn.fetch(query, *params)
                    else:
                        rows = await conn.fetch(query)
                    return [dict(row) for row in rows]
                    
                elif self.db_type == 'oracle':
                    cursor = await conn.cursor()
                    if params:
                        await cursor.execute(query, params)
                    else:
                        await cursor.execute(query)
                    rows = await cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
                    
        except Exception as e:
            logger.error(f"Async query execution failed: {e}")
            raise
    
    async def close(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()


class BatchProcessor:
    """
    High-performance batch processing for embedding and indexing operations.
    """
    
    def __init__(self, 
                 batch_size: int = 100,
                 max_workers: int = 4,
                 queue_size: int = 1000):
        """
        Initialize batch processor.
        
        Args:
            batch_size: Number of items per batch
            max_workers: Maximum worker threads
            queue_size: Maximum queue size
        """
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.queue_size = queue_size
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.processing_queue = asyncio.Queue(maxsize=queue_size)
    
    async def process_batch(self, 
                          items: List[Any],
                          processor_func: Callable,
                          *args, **kwargs) -> List[Any]:
        """
        Process items in batches using thread pool.
        
        Args:
            items: Items to process
            processor_func: Function to process each batch
            *args, **kwargs: Additional arguments for processor function
        
        Returns:
            List of processing results
        """
        if not items:
            return []
        
        # Split into batches
        batches = [
            items[i:i + self.batch_size]
            for i in range(0, len(items), self.batch_size)
        ]
        
        logger.info(f"Processing {len(items)} items in {len(batches)} batches")
        
        # Process batches concurrently
        loop = asyncio.get_event_loop()
        futures = []
        
        for batch in batches:
            future = loop.run_in_executor(
                self.executor, 
                processor_func, 
                batch, 
                *args, 
                **kwargs
            )
            futures.append(future)
        
        # Collect results
        results = []
        for future in as_completed(futures):
            try:
                batch_result = await asyncio.wrap_future(future)
                if isinstance(batch_result, list):
                    results.extend(batch_result)
                else:
                    results.append(batch_result)
            except Exception as e:
                logger.error(f"Batch processing error: {e}")
                continue
        
        logger.info(f"Batch processing completed: {len(results)} results")
        return results
    
    def shutdown(self):
        """Shutdown the batch processor."""
        self.executor.shutdown(wait=True)


class CircuitBreaker:
    """
    Circuit breaker pattern for resilience against cascading failures.
    """
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 timeout: int = 60,
                 expected_exception: type = Exception):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before trying again
            expected_exception: Exception type to catch
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Call function through circuit breaker.
        """
        with self._lock:
            # Check if circuit should be closed
            if self.state == "open":
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = "half-open"
                    self.failure_count = 0
                else:
                    raise Exception("Circuit breaker is OPEN")
            
            try:
                result = func(*args, **kwargs)
                
                # Success - reset if we were half-open
                if self.state == "half-open":
                    self.state = "closed"
                    self.failure_count = 0
                
                return result
                
            except self.expected_exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                # Open circuit if threshold reached
                if self.failure_count >= self.failure_threshold:
                    self.state = "open"
                    logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
                
                raise e


class RetryMechanism:
    """
    Configurable retry mechanism with exponential backoff.
    """
    
    def __init__(self, 
                 max_attempts: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0):
        """
        Initialize retry mechanism.
        
        Args:
            max_attempts: Maximum retry attempts
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
    
    def retry(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with retry logic.
        """
        last_exception = None
        
        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)
                
            except Exception as e:
                last_exception = e
                
                if attempt == self.max_attempts - 1:
                    # Last attempt failed
                    break
                
                # Calculate delay
                delay = min(
                    self.base_delay * (self.exponential_base ** attempt),
                    self.max_delay
                )
                
                logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}")
                time.sleep(delay)
        
        # All attempts failed
        raise last_exception


class PerformanceOptimizer:
    """
    Main performance optimization manager.
    """
    
    def __init__(self,
                 cache_config: Optional[Dict[str, Any]] = None,
                 db_config: Optional[Dict[str, Any]] = None,
                 batch_config: Optional[Dict[str, Any]] = None):
        """
        Initialize performance optimizer.
        
        Args:
            cache_config: Cache configuration
            db_config: Database configuration  
            batch_config: Batch processing configuration
        """
        # Initialize cache manager
        cache_config = cache_config or {}
        self.cache_manager = CacheManager(
            use_redis=cache_config.get("use_redis", False),
            redis_url=cache_config.get("redis_url"),
            memory_cache_size=cache_config.get("memory_cache_size", 10000),
            default_ttl=cache_config.get("default_ttl", 3600)
        )
        
        # Initialize database pool
        self.db_pool = None
        if db_config and ASYNC_DB_AVAILABLE:
            self.db_pool = AsyncDatabasePool(
                db_type=db_config.get("db_type", "oracle"),
                connection_string=db_config.get("connection_string"),
                pool_size=db_config.get("pool_size", 20),
                max_overflow=db_config.get("max_overflow", 10)
            )
        
        # Initialize batch processor
        batch_config = batch_config or {}
        self.batch_processor = BatchProcessor(
            batch_size=batch_config.get("batch_size", 100),
            max_workers=batch_config.get("max_workers", 4),
            queue_size=batch_config.get("queue_size", 1000)
        )
        
        # Circuit breakers for external services
        self.circuit_breakers = {
            "embedding": CircuitBreaker(failure_threshold=5, timeout=60),
            "database": CircuitBreaker(failure_threshold=3, timeout=30),
            "llm": CircuitBreaker(failure_threshold=5, timeout=120)
        }
        
        # Retry mechanisms
        self.retry_mechanisms = {
            "embedding": RetryMechanism(max_attempts=3, base_delay=1.0),
            "database": RetryMechanism(max_attempts=2, base_delay=0.5),
            "llm": RetryMechanism(max_attempts=3, base_delay=2.0)
        }
        
        logger.info("Performance optimizer initialized")
    
    def get_cache_manager(self) -> CacheManager:
        """Get cache manager instance."""
        return self.cache_manager
    
    def get_cached_decorator(self, ttl: Optional[int] = None, key_parts: Optional[List[str]] = None):
        """Get cached decorator for functions."""
        return cached(self.cache_manager, ttl, key_parts)
    
    async def get_db_pool(self) -> Optional[AsyncDatabasePool]:
        """Get async database pool."""
        if self.db_pool and not self.db_pool.pool:
            await self.db_pool.initialize()
        return self.db_pool
    
    def get_batch_processor(self) -> BatchProcessor:
        """Get batch processor instance."""
        return self.batch_processor
    
    def with_circuit_breaker(self, service: str, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if service not in self.circuit_breakers:
            return func(*args, **kwargs)
        
        return self.circuit_breakers[service].call(func, *args, **kwargs)
    
    def with_retry(self, service: str, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry mechanism."""
        if service not in self.retry_mechanisms:
            return func(*args, **kwargs)
        
        return self.retry_mechanisms[service].retry(func, *args, **kwargs)
    
    def with_resilience(self, service: str, func: Callable, *args, **kwargs) -> Any:
        """Execute function with both circuit breaker and retry."""
        def resilient_func():
            return self.with_circuit_breaker(service, func, *args, **kwargs)
        
        return self.with_retry(service, resilient_func)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        stats = {
            "cache": self.cache_manager.memory_cache.get_stats(),
            "circuit_breakers": {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Circuit breaker states
        for name, cb in self.circuit_breakers.items():
            stats["circuit_breakers"][name] = {
                "state": cb.state,
                "failure_count": cb.failure_count,
                "last_failure": cb.last_failure_time
            }
        
        return stats
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.db_pool:
            await self.db_pool.close()
        
        self.batch_processor.shutdown()