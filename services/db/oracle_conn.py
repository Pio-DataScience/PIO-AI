"""
Oracle Connection Pool with Safety Features
Provides secure, pooled connections to Oracle database with circuit breaker pattern.
"""
import logging
import time
import threading
from contextlib import contextmanager
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
import hashlib
import json

try:
    import oracledb
    ORACLE_AVAILABLE = True
    # Use the modern oracledb driver (replaces cx_Oracle)
    cx_Oracle = oracledb  # Compatibility alias
except ImportError:
    ORACLE_AVAILABLE = False

logger = logging.getLogger(__name__)

class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open" 
    HALF_OPEN = "half_open"

@dataclass
class ConnectionConfig:
    """Oracle connection configuration."""
    dsn: str
    user: str
    password: str
    use_dba_views: bool = True
    pool_min: int = 1
    pool_max: int = 4
    stmt_cache: int = 50
    fetch_arraysize: int = 1000
    connect_timeout: int = 30
    query_timeout: int = 300
    retry_attempts: int = 3
    retry_backoff_factor: float = 2.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: int = 60

class CircuitBreaker:
    """Circuit breaker for database operations."""
    
    def __init__(self, failure_threshold: int, reset_timeout: int):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = threading.Lock()
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if time.time() - self.last_failure_time > self.reset_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker moved to HALF_OPEN state")
                else:
                    raise Exception("Circuit breaker is OPEN - operation not allowed")
            
            try:
                result = func(*args, **kwargs)
                if self.state == CircuitBreakerState.HALF_OPEN:
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
                    logger.info("Circuit breaker moved to CLOSED state")
                return result
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitBreakerState.OPEN
                    logger.error(f"Circuit breaker moved to OPEN state after {self.failure_count} failures")
                
                logger.error(f"Circuit breaker failure {self.failure_count}: {e}")
                raise

class OracleConnectionPool:
    """Thread-safe Oracle connection pool with safety features."""
    
    def __init__(self, config: ConnectionConfig):
        if not ORACLE_AVAILABLE:
            raise ImportError("cx_Oracle is required for Oracle connectivity")
        
        self.config = config
        self._pool = None
        self._circuit_breaker = CircuitBreaker(
            config.circuit_breaker_failure_threshold,
            config.circuit_breaker_reset_timeout
        )
        self._query_stats = {}
        self._stats_lock = threading.Lock()
        self._init_pool()
    
    def _init_pool(self):
        """Initialize the Oracle connection pool."""
        try:
            self._pool = cx_Oracle.SessionPool(
                user=self.config.user,
                password=self.config.password,
                dsn=self.config.dsn,
                min=self.config.pool_min,
                max=self.config.pool_max,
                increment=1,
                threaded=True,
                getmode=cx_Oracle.SPOOL_ATTRVAL_WAIT,
                timeout=self.config.connect_timeout
            )
            logger.info(f"Oracle connection pool initialized: {self.config.pool_min}-{self.config.pool_max} connections")
        except Exception as e:
            logger.error(f"Failed to initialize Oracle connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool with proper cleanup."""
        connection = None
        try:
            connection = self._circuit_breaker.call(self._pool.acquire)
            connection.stmtcachesize = self.config.stmt_cache
            connection.arraysize = self.config.fetch_arraysize
            yield connection
        except Exception as e:
            logger.error(f"Connection error: {e}")
            raise
        finally:
            if connection:
                try:
                    self._pool.release(connection)
                except Exception as e:
                    logger.error(f"Failed to release connection: {e}")
    
    def _get_sql_hash(self, sql: str) -> str:
        """Generate hash for SQL statement (for logging/stats)."""
        return hashlib.md5(sql.encode('utf-8')).hexdigest()[:8]
    
    def _log_query_stats(self, sql_hash: str, elapsed_ms: float, rows: int, attempt: int):
        """Log query performance statistics."""
        with self._stats_lock:
            if sql_hash not in self._query_stats:
                self._query_stats[sql_hash] = {
                    'calls': 0,
                    'total_time': 0,
                    'avg_time': 0,
                    'total_rows': 0,
                    'failures': 0
                }
            
            stats = self._query_stats[sql_hash]
            stats['calls'] += 1
            stats['total_time'] += elapsed_ms
            stats['avg_time'] = stats['total_time'] / stats['calls']
            stats['total_rows'] += rows
            
            if attempt > 1:
                stats['failures'] += attempt - 1
        
        logger.info(
            f"Query stats - hash:{sql_hash}, elapsed:{elapsed_ms:.2f}ms, "
            f"rows:{rows}, attempt:{attempt}, circuit:{self._circuit_breaker.state.value}"
        )
    
    def execute_query(self, sql: str, binds: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query with safety features.
        
        Args:
            sql: SQL query string (must be SELECT only)
            binds: Dictionary of bind parameters
            
        Returns:
            List of result rows as dictionaries
            
        Raises:
            ValueError: If SQL is not a SELECT statement
            Exception: Various database and circuit breaker exceptions
        """
        # Safety check: ensure it's a SELECT statement
        sql_stripped = sql.strip().upper()
        if not sql_stripped.startswith('SELECT'):
            raise ValueError("Only SELECT statements are allowed")
        
        # Validate no dangerous keywords
        dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE']
        for keyword in dangerous_keywords:
            if keyword in sql_stripped:
                raise ValueError(f"Dangerous keyword '{keyword}' found in SQL")
        
        sql_hash = self._get_sql_hash(sql)
        binds = binds or {}
        
        for attempt in range(1, self.config.retry_attempts + 1):
            start_time = time.time()
            
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(sql, binds)
                    
                    # Get column names
                    columns = [desc[0] for desc in cursor.description]
                    
                    # Fetch all results
                    rows = cursor.fetchall()
                    
                    # Convert to list of dictionaries
                    results = [dict(zip(columns, row)) for row in rows]
                    
                    elapsed_ms = (time.time() - start_time) * 1000
                    self._log_query_stats(sql_hash, elapsed_ms, len(results), attempt)
                    
                    return results
                    
            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"Query attempt {attempt} failed - hash:{sql_hash}, "
                    f"elapsed:{elapsed_ms:.2f}ms, error:{e}"
                )
                
                if attempt == self.config.retry_attempts:
                    self._log_query_stats(sql_hash, elapsed_ms, 0, attempt)
                    raise
                
                # Exponential backoff
                wait_time = self.config.retry_backoff_factor ** (attempt - 1)
                time.sleep(wait_time)
        
        # Should never reach here
        raise Exception("Query execution failed after all retries")
    
    def test_connection(self) -> Dict[str, Any]:
        """Test the database connection and return status."""
        try:
            start_time = time.time()
            results = self.execute_query("SELECT SYSDATE FROM DUAL")
            elapsed_ms = (time.time() - start_time) * 1000
            
            return {
                "status": "healthy",
                "response_time_ms": elapsed_ms,
                "sysdate": results[0]['SYSDATE'] if results else None,
                "circuit_breaker_state": self._circuit_breaker.state.value,
                "pool_busy_connections": self._pool.busy if self._pool else 0,
                "pool_open_connections": self._pool.opened if self._pool else 0
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "circuit_breaker_state": self._circuit_breaker.state.value
            }
    
    def get_query_stats(self) -> Dict[str, Any]:
        """Get query performance statistics."""
        with self._stats_lock:
            return {
                "total_queries": len(self._query_stats),
                "circuit_breaker_state": self._circuit_breaker.state.value,
                "circuit_breaker_failures": self._circuit_breaker.failure_count,
                "query_details": dict(self._query_stats)
            }
    
    def close(self):
        """Close the connection pool."""
        if self._pool:
            try:
                self._pool.close(force=True)
                logger.info("Oracle connection pool closed")
            except Exception as e:
                logger.error(f"Error closing connection pool: {e}")

# Global connection pool instance
_connection_pool: Optional[OracleConnectionPool] = None
_pool_lock = threading.Lock()

def initialize_connection_pool(config: ConnectionConfig):
    """Initialize the global connection pool."""
    global _connection_pool
    with _pool_lock:
        if _connection_pool:
            _connection_pool.close()
        _connection_pool = OracleConnectionPool(config)

def get_connection_pool() -> OracleConnectionPool:
    """Get the global connection pool instance."""
    global _connection_pool
    if not _connection_pool:
        raise RuntimeError("Connection pool not initialized. Call initialize_connection_pool() first.")
    return _connection_pool

def safe_execute_query(sql: str, binds: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Convenience function for executing queries safely.
    
    Args:
        sql: SQL query string (SELECT only)
        binds: Dictionary of bind parameters
        
    Returns:
        List of result rows as dictionaries
    """
    pool = get_connection_pool()
    return pool.execute_query(sql, binds)