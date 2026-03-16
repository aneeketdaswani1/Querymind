"""Query executor module for QueryMind.

Executes validated SQL queries against the PostgreSQL database using safe, read-only
database connections and handles result retrieval and formatting.
"""

import time
from typing import List, Dict, Any, Tuple
from datetime import datetime, date
import structlog
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor

from agent.config import AGENT_DATABASE_URL, QUERY_TIMEOUT_SECONDS, MAX_RESULT_ROWS

logger = structlog.get_logger(__name__)


class DateTimeEncoder:
    """Helper to serialize datetime/date objects to ISO format strings."""
    
    @staticmethod
    def serialize(obj: Any) -> Any:
        """Convert datetime/date objects to ISO format strings."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return obj


class QueryExecutor:
    """
    Executes validated SQL queries against PostgreSQL with safety controls.
    
    Features:
    - Connection pooling for efficiency
    - Query timeout enforcement
    - Result row limiting
    - Clean error messages
    - Execution timing
    """
    
    def __init__(self, database_url: str = AGENT_DATABASE_URL, pool_size: int = 5):
        """
        Initialize QueryExecutor with connection pool.
        
        Args:
            database_url: PostgreSQL connection string
            pool_size: Number of connections to maintain in pool
        """
        self.database_url = database_url
        self.pool = None
        self.pool_size = pool_size
        
        # Initialize connection pool
        try:
            self.pool = SimpleConnectionPool(1, pool_size, database_url)
            logger.info("query_executor_initialized", pool_size=pool_size)
        except Exception as e:
            logger.error("failed_to_initialize_pool", error=str(e))
            raise
    
    async def execute(
        self,
        sql: str,
        limit: int = MAX_RESULT_ROWS
    ) -> Tuple[List[Dict[str, Any]], int, float, str]:
        """
        Execute SQL query and return results.
        
        Args:
            sql: Validated SQL query (already passed safety checks)
            limit: Maximum rows to return (default MAX_RESULT_ROWS)
        
        Returns:
            Tuple of (results, row_count, execution_time_ms, error_message)
            - results: List of rows as dictionaries
            - row_count: Number of rows returned
            - execution_time_ms: Query execution time in milliseconds
            - error_message: Empty string if successful, error text if failed
        """
        conn = None
        cursor = None
        start_time = time.time()
        
        try:
            # Add LIMIT if not already present (safety measure)
            query_with_limit = self._add_limit_to_query(sql, limit)
            
            logger.debug("executing_query", limit=limit, sql_length=len(sql))
            
            # Get connection from pool
            conn = self.pool.getconn()
            conn.set_session(readonly=True)  # Enforce read-only at connection level
            
            # Set query timeout
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f"SET statement_timeout TO {QUERY_TIMEOUT_SECONDS * 1000};")
                
                # Execute query
                cursor.execute(query_with_limit)
                
                # Fetch all results
                rows = cursor.fetchall()
                row_count = len(rows)
            
            # Convert rows to dicts and serialize datetime objects
            results = [self._serialize_row(dict(row)) for row in rows]
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.info(
                "query_executed_successfully",
                row_count=row_count,
                execution_time_ms=execution_time_ms
            )
            
            return results, row_count, execution_time_ms, ""
        
        except psycopg2.OperationalError as e:
            error_msg = f"Database connection error: {str(e)}"
            logger.error("database_operational_error", error=error_msg)
            return [], 0, (time.time() - start_time) * 1000, error_msg
        
        except psycopg2.ProgrammingError as e:
            # SQL syntax or schema error
            error_msg = f"SQL syntax error: {str(e)}"
            logger.error("sql_syntax_error", error=error_msg, sql=sql[:200])
            return [], 0, (time.time() - start_time) * 1000, error_msg
        
        except psycopg2.InternalError as e:
            # Transaction/internal DB error
            error_msg = f"Database internal error (transaction aborted): {str(e)}"
            logger.error("database_internal_error", error=error_msg)
            return [], 0, (time.time() - start_time) * 1000, error_msg
        
        except psycopg2.Error as e:
            # Generic PostgreSQL error
            error_msg = f"Database error: {str(e)}"
            logger.error("database_error", error=error_msg)
            return [], 0, (time.time() - start_time) * 1000, error_msg
        
        except Exception as e:
            error_msg = f"Unexpected error during query execution: {str(e)}"
            logger.error("unexpected_error", error=error_msg)
            return [], 0, (time.time() - start_time) * 1000, error_msg
        
        finally:
            # Return connection to pool
            if conn:
                try:
                    self.pool.putconn(conn)
                except Exception as e:
                    logger.warning("error_returning_connection", error=str(e))
    
    def _add_limit_to_query(self, sql: str, limit: int) -> str:
        """
        Add a LIMIT clause to query if not already present.
        
        Args:
            sql: SQL query
            limit: Limit value to add
        
        Returns:
            Query with LIMIT clause
        """
        sql_upper = sql.upper().strip()
        
        # If query already has LIMIT, don't add another
        if "LIMIT" in sql_upper:
            return sql
        
        # Add LIMIT at the end
        return f"{sql.rstrip(';')} LIMIT {limit};"
    
    def _serialize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serialize a row, converting datetime/date objects to ISO strings.
        
        Args:
            row: Dictionary row from database
        
        Returns:
            Serialized row
        """
        serialized = {}
        for key, value in row.items():
            serialized[key] = DateTimeEncoder.serialize(value)
        return serialized
    
    def close(self):
        """Close all connections in the pool."""
        if self.pool:
            self.pool.closeall()
            logger.info("connection_pool_closed")

