"""Safety checker module for QueryMind.

Validates generated SQL before execution. This is the most critical component.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import sqlparse
import structlog
from sqlglot import exp, parse_one

logger = structlog.get_logger(__name__)


@dataclass
class SafetyResult:
    """Structured result from safety checks."""

    passed: bool
    reason: str
    sanitized_sql: str = ""


class SafetyChecker:
    """Validates generated SQL before execution."""

    BLOCKED_KEYWORDS = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "EXEC",
        "EXECUTE",
        "GRANT",
        "REVOKE",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "INTO OUTFILE",
        "LOAD_FILE",
        "pg_sleep",
        "COPY",
        "\\copy",
    ]

    MAX_RESULT_ROWS = 500
    MAX_QUERY_LENGTH = 2000
    DEFAULT_LIMIT = 100
    LARGE_TABLE_ROW_THRESHOLD = 100000

    def check(self, sql: str, schema: Optional[Dict[str, Any]] = None) -> SafetyResult:
        """Validate SQL and return pass/fail with sanitized SQL.

        Checks (in order):
        1. Parse SQL with sqlparse
        2. Verify SELECT / WITH...SELECT read-only shape
        3. Check blocked keywords (case-insensitive whole-word)
        4. Check injection patterns
        5. Verify query length
        6. Ensure LIMIT exists (adds LIMIT 100 if missing)
        7. Check expensive patterns
        8. Verify referenced tables exist
        9. Verify referenced columns exist
        """
        if not sql or not isinstance(sql, str):
            return SafetyResult(False, "SQL query is empty or invalid type", "")

        normalized = self._sanitize_sql(sql)

        # 1) Parse validity and single statement check
        parsed = sqlparse.parse(normalized)
        if not parsed:
            return SafetyResult(False, "SQL parsing failed", "")
        if len(parsed) != 1:
            return SafetyResult(False, "Only a single SQL statement is allowed", "")
        if not str(parsed[0]).strip():
            return SafetyResult(False, "SQL statement is empty", "")

        # 2) Read-only SELECT verification
        if not self._is_read_only(normalized):
            return SafetyResult(False, "Only SELECT statements are allowed", "")

        # 3) Blocked keyword checks
        blocked = self._find_blocked_keywords(normalized)
        if blocked:
            return SafetyResult(False, f"Blocked keyword detected: {blocked}", "")

        # 4) Injection pattern checks
        injection_ok, injection_reason = self._check_injection_patterns(normalized)
        if not injection_ok:
            return SafetyResult(False, injection_reason, "")

        # 5) Length check
        if len(normalized) > self.MAX_QUERY_LENGTH:
            return SafetyResult(
                False,
                f"Query length {len(normalized)} exceeds max {self.MAX_QUERY_LENGTH}",
                "",
            )

        # 6) LIMIT enforcement
        sanitized = self._enforce_limit(normalized)

        # 7) Expensive pattern checks
        expensive_ok, expensive_reason = self._check_expensive_patterns(sanitized, schema or {})
        if not expensive_ok:
            return SafetyResult(False, expensive_reason, "")

        # 8-9) Table/column reference checks
        if schema is None:
            return SafetyResult(False, "Schema is required for table/column validation", "")

        refs_ok, refs_reason = self._validate_references(sanitized, schema)
        if not refs_ok:
            return SafetyResult(False, refs_reason, "")

        logger.info("safety_check_passed")
        return SafetyResult(True, "Query passed all safety checks", sanitized)

    def _sanitize_sql(self, sql: str) -> str:
        """Normalize whitespace and strip trailing semicolons."""
        collapsed = re.sub(r"\s+", " ", sql).strip()
        return collapsed.rstrip(";")

    def _is_read_only(self, sql: str) -> bool:
        """Uses sqlparse to verify the statement type is SELECT."""
        statements = sqlparse.parse(sql)
        if not statements:
            return False

        statement = statements[0]
        statement_type = statement.get_type().upper()
        if statement_type != "SELECT":
            return False

        return True

    def _find_blocked_keywords(self, sql: str) -> str:
        """Return first blocked keyword found, or empty string."""
        upper_sql = sql.upper()
        for keyword in self.BLOCKED_KEYWORDS:
            if " " in keyword:
                pattern = re.escape(keyword)
            elif keyword.startswith("\\"):
                pattern = re.escape(keyword)
            else:
                pattern = rf"\b{re.escape(keyword)}\b"

            if re.search(pattern, upper_sql, flags=re.IGNORECASE):
                return keyword
        return ""

    def _check_injection_patterns(self, sql: str) -> Tuple[bool, str]:
        """Detect common SQL injection patterns."""
        # ; followed by another statement (allow one optional trailing semicolon already removed)
        if re.search(r";\s*\S", sql):
            return False, "Multiple statements detected (possible injection)"

        # Inline or block comments can hide malicious payloads.
        if "--" in sql or "/*" in sql or "*/" in sql or "#" in sql:
            return False, "SQL comments are not allowed"

        # Attempt to detect UNION shape mismatch by projected column counts.
        union_parts = re.split(r"\bUNION(?:\s+ALL)?\b", sql, flags=re.IGNORECASE)
        if len(union_parts) > 1:
            counts = [self._count_selected_columns(part) for part in union_parts]
            if any(c <= 0 for c in counts):
                return False, "Unable to validate UNION column consistency"
            if len(set(counts)) != 1:
                return False, "UNION statements must have the same number of selected columns"

        return True, ""

    def _count_selected_columns(self, sql_segment: str) -> int:
        """Best-effort projected column count for a SELECT segment."""
        try:
            ast = parse_one(sql_segment, read="postgres")
            select_expr = ast.find(exp.Select)
            if not select_expr:
                return -1
            return len(select_expr.expressions)
        except Exception:
            match = re.search(
                r"\bSELECT\b\s+(.*?)\s+\bFROM\b",
                sql_segment,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not match:
                return -1
            body = match.group(1)
            return body.count(",") + 1

    def _enforce_limit(self, sql: str) -> str:
        """Ensure LIMIT exists; add LIMIT 100 if not present; cap to MAX_RESULT_ROWS."""
        limit_match = re.search(r"\bLIMIT\s+(\d+)\b", sql, flags=re.IGNORECASE)
        if limit_match:
            current_limit = int(limit_match.group(1))
            if current_limit > self.MAX_RESULT_ROWS:
                return re.sub(
                    r"\bLIMIT\s+\d+\b",
                    f"LIMIT {self.MAX_RESULT_ROWS}",
                    sql,
                    flags=re.IGNORECASE,
                )
            return sql

        return f"{sql} LIMIT {self.DEFAULT_LIMIT}"

    def _check_expensive_patterns(self, sql: str, schema: Dict[str, Any]) -> Tuple[bool, str]:
        """Detect expensive query shapes that should be rejected."""
        if re.search(r"\bCROSS\s+JOIN\b", sql, flags=re.IGNORECASE):
            return False, "CROSS JOIN is blocked due to high execution risk"

        nested_subquery_count = len(re.findall(r"\(\s*SELECT\b", sql, flags=re.IGNORECASE))
        if nested_subquery_count > 3:
            return False, "Nested subqueries deeper than 3 levels are blocked"

        try:
            ast = parse_one(sql, read="postgres")
            has_where = ast.args.get("where") is not None
            has_star = any(isinstance(node, exp.Star) for node in ast.find_all(exp.Star))
            if has_star and not has_where:
                tables = [t.name.lower() for t in ast.find_all(exp.Table) if t.name]
                for table in tables:
                    table_meta = schema.get(table, {})
                    row_count = int(table_meta.get("row_count", 0))
                    if row_count >= self.LARGE_TABLE_ROW_THRESHOLD:
                        return (
                            False,
                            f"SELECT * without WHERE is blocked for large table '{table}'",
                        )
        except Exception:
            # If AST analysis fails, do not hard-fail here; other checks still protect execution.
            pass

        return True, ""

    def _validate_references(self, sql: str, schema: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify all table.column references exist in the actual schema."""
        try:
            ast = parse_one(sql, read="postgres")
        except Exception as exc:
            return False, f"SQL parse error during reference validation: {exc}"

        if not schema:
            return False, "Schema dictionary is empty"

        schema_tables = {name.lower(): meta for name, meta in schema.items()}
        table_columns: Dict[str, set[str]] = {}
        for table_name, meta in schema_tables.items():
            cols = meta.get("columns", [])
            col_names = {str(c.get("name", "")).lower() for c in cols if c.get("name")}
            table_columns[table_name] = col_names

        alias_to_table: Dict[str, str] = {}
        referenced_tables: set[str] = set()

        for table_expr in ast.find_all(exp.Table):
            table_name = (table_expr.name or "").lower()
            if not table_name:
                continue
            if table_name not in schema_tables:
                return False, f"Referenced table '{table_name}' does not exist"

            referenced_tables.add(table_name)
            alias = (table_expr.alias_or_name or table_name).lower()
            alias_to_table[alias] = table_name

        if not referenced_tables:
            return False, "No referenced tables found in query"

        for col_expr in ast.find_all(exp.Column):
            col_name = (col_expr.name or "").lower()
            if not col_name or col_name == "*":
                continue

            table_alias = (col_expr.table or "").lower()
            if table_alias:
                resolved_table = alias_to_table.get(table_alias, table_alias)
                if resolved_table not in table_columns:
                    return False, f"Referenced table/alias '{table_alias}' does not exist"
                if col_name not in table_columns[resolved_table]:
                    return False, f"Column '{resolved_table}.{col_name}' does not exist"
            else:
                matching_tables = [
                    t for t in referenced_tables if col_name in table_columns.get(t, set())
                ]
                if not matching_tables:
                    return False, f"Unqualified column '{col_name}' does not exist"

        return True, ""
