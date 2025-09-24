"""
Modern SQL Executor - Safe, monitored database query execution.
Production-ready with comprehensive safety, timeouts, and observability.
Uses modern oracledb library (replacement for deprecated cx_Oracle).
"""

import asyncio
import time
from typing import Dict, List, Any, Optional

try:
    import oracledb
    ORACLE_AVAILABLE = True
    # Use the modern oracledb driver (replaces cx_Oracle)
    cx_Oracle = oracledb  # Compatibility alias
except ImportError:
    ORACLE_AVAILABLE = False

from .observability import get_observability, log_performance

logger, tracer = get_observability()


class SQLExecutor:
    """
    Production SQL executor with safety limits, monitoring, and graceful error handling.
    """
    
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.connection_pool = None
        
        # Safety limits
        self.max_rows = 1000
        self.default_timeout = 30
        self.max_timeout = 120
        
        logger.log_operation(
            component="sql_executor",
            operation="initialize",
            phase="complete",
            outcome="success",
            has_config=bool(db_config)
        )
    
    async def execute_query(self, 
                           sql_query: str, 
                           limit: int = 100, 
                           timeout_seconds: int = 30) -> Dict[str, Any]:
        """
        Execute SQL query with comprehensive safety and monitoring.
        """
        
        start_time = time.time()
        
        # Validate inputs
        if not sql_query or not sql_query.strip():
            return {
                "results": [],
                "error": "Empty SQL query",
                "execution_time_ms": 0,
                "row_count": 0
            }
        
        if not self.db_config:
            return {
                "results": [],
                "error": "Database configuration not available",
                "execution_time_ms": 0,
                "row_count": 0
            }
        
        # Enhanced safety validation - ensure only SELECT statements
        sql_stripped = sql_query.strip().upper()
        if not sql_stripped.startswith('SELECT'):
            return {
                "results": [],
                "error": "Only SELECT statements are allowed for safety",
                "execution_time_ms": 0,
                "row_count": 0
            }
        
        # Check for dangerous keywords
        dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE', 'GRANT', 'REVOKE']
        for keyword in dangerous_keywords:
            if keyword in sql_stripped:
                return {
                    "results": [],
                    "error": f"Dangerous keyword '{keyword}' found in SQL - operation not allowed",
                    "execution_time_ms": 0,
                    "row_count": 0
                }
        
        # Apply safety limits
        safe_limit = min(limit, self.max_rows)
        safe_timeout = min(timeout_seconds, self.max_timeout)
        
        # Add ROWNUM limit if not present
        safe_sql = self._add_row_limit(sql_query, safe_limit)
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_sql_internal(safe_sql),
                timeout=safe_timeout
            )
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.log_operation(
                component="sql_executor",
                operation="execute_query",
                phase="complete",
                outcome="success",
                duration_ms=execution_time_ms,
                row_count=len(result.get("results", [])),
                sql_length=len(safe_sql)
            )
            
            result["execution_time_ms"] = execution_time_ms
            return result
            
        except asyncio.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.log_operation(
                component="sql_executor", 
                operation="execute_query",
                phase="timeout",
                outcome="error",
                duration_ms=execution_time_ms,
                timeout_seconds=safe_timeout
            )
            
            return {
                "results": [],
                "error": f"Query timed out after {safe_timeout} seconds",
                "execution_time_ms": execution_time_ms,
                "row_count": 0
            }
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.log_error("sql_executor", "execute_query", e, 
                           duration_ms=execution_time_ms,
                           sql_query=safe_sql[:200])
            
            return {
                "results": [],
                "error": f"Database error: {str(e)}",
                "execution_time_ms": execution_time_ms,
                "row_count": 0
            }
    
    async def _execute_sql_internal(self, sql_query: str) -> Dict[str, Any]:
        """Internal SQL execution with proper connection handling."""
        
        connection = None
        cursor = None
        
        try:
            # Create connection
            connection = self._create_connection()
            cursor = connection.cursor()
            
            # Execute query
            cursor.execute(sql_query)
            
            # Fetch results
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            results = []
            for row in rows:
                row_dict = {}
                for i, column in enumerate(columns):
                    value = row[i]
                    # Handle Oracle specific types with oracledb
                    if hasattr(value, 'read'):  # CLOB/BLOB
                        value = value.read()
                    elif hasattr(value, 'strftime'):  # DATE/TIMESTAMP
                        value = value.isoformat()
                    elif isinstance(value, oracledb.LOB):  # Handle LOB types explicitly
                        value = value.read() if value else None
                    row_dict[column] = value
                results.append(row_dict)
            
            return {
                "results": results,
                "columns": columns,
                "row_count": len(results),
                "success": True
            }
            
        except Exception as e:
            raise e
            
        finally:
            # Clean up resources
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if connection:
                try:
                    connection.close()
                except:
                    pass
    
    def _create_connection(self):
        """Create Oracle database connection."""
        
        if not ORACLE_AVAILABLE:
            raise ValueError("oracledb not available - install with 'pip install oracledb'")
        
        dsn = self.db_config.get('dsn')
        user = self.db_config.get('user')
        password = self.db_config.get('password')
        
        if not all([dsn, user, password]):
            raise ValueError("Incomplete database configuration")
        
        # Create connection with timeout using modern oracledb
        connection = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            encoding="UTF-8"
        )
        
        return connection
    
    def _add_row_limit(self, sql_query: str, limit: int) -> str:
        """Add ROWNUM limit to SQL query if not present."""
        
        sql_upper = sql_query.upper().strip()
        
        # Check if ROWNUM or LIMIT already present
        if 'ROWNUM' in sql_upper or 'LIMIT' in sql_upper:
            return sql_query
        
        # Add WHERE clause with ROWNUM
        if 'WHERE' in sql_upper:
            # Insert ROWNUM condition into existing WHERE
            where_pos = sql_upper.find('WHERE')
            before_where = sql_query[:where_pos + 5]  # Include "WHERE"
            after_where = sql_query[where_pos + 5:]
            return f"{before_where} ROWNUM <= {limit} AND ({after_where.strip()})"
        elif 'ORDER BY' in sql_upper:
            # Insert WHERE before ORDER BY
            order_pos = sql_upper.find('ORDER BY')
            before_order = sql_query[:order_pos]
            after_order = sql_query[order_pos:]
            return f"{before_order.strip()} WHERE ROWNUM <= {limit} {after_order}"
        else:
            # Add WHERE clause at the end
            return f"{sql_query.rstrip()} WHERE ROWNUM <= {limit}"
    
    @log_performance("sql_executor", "test_connection")
    def test_connection(self) -> Dict[str, Any]:
        """Test database connection health."""
        
        try:
            connection = self._create_connection()
            cursor = connection.cursor()
            
            # Simple test query
            cursor.execute("SELECT 1 FROM DUAL")
            result = cursor.fetchone()
            
            cursor.close()
            connection.close()
            
            if result and result[0] == 1:
                return {
                    "status": "healthy",
                    "message": "Database connection successful"
                }
            else:
                return {
                    "status": "unhealthy", 
                    "message": "Unexpected test query result"
                }
                
        except Exception as e:
            logger.log_error("sql_executor", "test_connection", e)
            return {
                "status": "error",
                "message": f"Connection failed: {str(e)}"
            }