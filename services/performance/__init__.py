"""
Performance services package initialization.
Provides high-performance caching, async I/O, and resilience patterns.
"""

__version__ = "1.0.0"

from .optimization import (
    CacheEntry,
    InMemoryCache,
    RedisCache,
    CacheManager,
    cached,
    AsyncDatabasePool,
    BatchProcessor,
    CircuitBreaker,
    RetryMechanism,
    PerformanceOptimizer,
    REDIS_AVAILABLE,
    ASYNC_DB_AVAILABLE
)

__all__ = [
    "CacheEntry",
    "InMemoryCache",
    "RedisCache", 
    "CacheManager",
    "cached",
    "AsyncDatabasePool",
    "BatchProcessor",
    "CircuitBreaker",
    "RetryMechanism",
    "PerformanceOptimizer",
    "REDIS_AVAILABLE",
    "ASYNC_DB_AVAILABLE"
]