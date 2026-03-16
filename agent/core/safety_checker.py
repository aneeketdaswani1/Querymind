"""Safety checker module for QueryMind.

Validates generated SQL queries to ensure safety, preventing dangerous operations like
INSERT, UPDATE, DELETE commands and enforcing read-only access patterns.
"""

import re
import structlog
from typing import Tuple

from agent.config import FORBIDDEN_SQL_KEYWORDS, ALLOWED_SQL_KEYWORDS

logger = structlog.get_logger(__name__)


class SafetyChecker:
    """
    Validates SQL queries for safety and read-only compliance.
    
    Enforces:
    - No INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE operations
    - Only SELECT and related read operations
    - No stored procedures or function definitions
    - No multiple statements (can't chain malicious statements)
    """
    
    def __init__(self):
        """Initialize SafetyChecker."""
        self.forbidden_keywords = FORBIDDEN_SQL_KEYWORDS
        logger.debug("safety_checker_initialized")
    
    def check(self, sql: str) -> Tuple[bool, str]:
        """
        Check if SQL query is safe to execute.
        
        Args:
            sql: SQL query string to validate
        
        Returns:
            Tuple of (is_safe: bool, reason: str)
            - is_safe=True if query passes all checks
            - reason explains why query failed if not safe
        """
        if not sql or not isinstance(sql, str):
            return False, "SQL query is empty or not a string"
        
        # Normalize SQL for analysis (uppercase, strip comments)
        sql_normalized = self._normalize_sql(sql)
        sql_upper = sql_normalized.upper()
        
        logger.debug("checking_sql_safety", sql_length=len(sql))
        
        # Check 1: Forbidden keywords
        forbidden_found = self._check_forbidden_keywords(sql_upper)
        if forbidden_found:
            reason = f"Query contains forbidden keyword(s): {', '.join(forbidden_found)}"
            logger.warning("safety_check_failed_forbidden_keywords", reason=reason)
            return False, reason
        
        # Check 2: Multiple statements (detect semicolons)
        if self._has_multiple_statements(sql_normalized):
            reason = "Query contains multiple statements (;) - not allowed"
            logger.warning("safety_check_failed_multiple_statements")
            return False, reason
        
        # Check 3: Comments that might hide malicious code
        if self._has_dangerous_comments(sql_normalized):
            reason = "Query contains potentially dangerous SQL comments"
            logger.warning("safety_check_failed_dangerous_comments")
            return False, reason
        
        # Check 4: Starts with SELECT
        if not sql_upper.strip().startswith(("SELECT", "WITH")):
            reason = "Query must start with SELECT or WITH (for CTEs)"
            logger.warning("safety_check_failed_not_select_start")
            return False, reason
        
        logger.info("safety_check_passed")
        return True, "Query passed all safety checks"
    
    def _normalize_sql(self, sql: str) -> str:
        """
        Normalize SQL by removing comments and extra whitespace.
        
        Args:
            sql: Raw SQL query
        
        Returns:
            Normalized SQL
        """
        # Remove single-line comments (--)
        sql = re.sub(r'--[^\n]*', '', sql)
        
        # Remove multi-line comments (/* ... */)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        
        # Reduce multiple whitespace to single space
        sql = re.sub(r'\s+', ' ', sql)
        
        return sql.strip()
    
    def _check_forbidden_keywords(self, sql_upper: str) -> set:
        """
        Find any forbidden keywords in the query.
        
        Args:
            sql_upper: Uppercase normalized SQL
        
        Returns:
            Set of forbidden keywords found, empty if none
        """
        found = set()
        
        for keyword in self.forbidden_keywords:
            # Use word boundary to avoid false positives (e.g., "create_date" column)
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, sql_upper):
                found.add(keyword)
        
        return found
    
    def _has_multiple_statements(self, sql: str) -> bool:
        """
        Check if query contains multiple statements.
        
        Args:
            sql: Normalized SQL
        
        Returns:
            True if multiple statements detected (semicolons)
        """
        # Count semicolons outside of string literals
        parts = re.split(r"['\"]", sql)
        semicolon_count = 0
        
        for i, part in enumerate(parts):
            if i % 2 == 0:  # Outside quotes
                semicolon_count += part.count(';')
        
        # More than one semicolon (or one at the very end that's not standard) is suspicious
        return semicolon_count > 1 or (semicolon_count == 1 and not sql.rstrip().endswith(';'))
    
    def _has_dangerous_comments(self, sql: str) -> bool:
        """
        Detect suspicious comment patterns that might hide code.
        
        Args:
            sql: Normalized SQL (comments already removed, but we check for patterns)
        
        Returns:
            True if dangerous patterns detected
        """
        # Check for patterns like /*!50000 ... */ (conditional execution hints)
        if re.search(r'/\*!', sql):
            return True
        
        # Check for # comments (MySQL style, could bypass checks)
        if re.search(r'#.*$', sql, re.MULTILINE):
            return True
        
        return False

