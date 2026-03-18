"""Configuration module for QueryMind agent.

Manages environment variables, settings, and configuration constants used throughout
the agent package including LLM, database, and runtime settings.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Dedicated read-only connection for all agent-generated SQL execution.
AGENT_DATABASE_URL = os.getenv(
    "AGENT_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql://querymind_readonly:querymind_readonly_password@localhost:5432/querymind",
    ),
)

# Separate application connection (for non-agent tasks such as logging/auditing).
APP_DATABASE_URL = os.getenv(
    "APP_DATABASE_URL",
    "postgresql://querymind_app:querymind_app_password@localhost:5432/querymind",
)

# Backward-compat alias; existing imports keep working.
DATABASE_URL = AGENT_DATABASE_URL

READONLY_USER = os.getenv("READONLY_USER", "querymind_readonly")

# ============================================================================
# LLM CONFIGURATION
# ============================================================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))

# ============================================================================
# REDIS CONFIGURATION (for caching/sessions)
# ============================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ============================================================================
# AGENT CONFIGURATION
# ============================================================================

# Maximum retries for SQL generation on error
MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", "2"))

# Query execution timeout in seconds
QUERY_TIMEOUT_SECONDS = int(os.getenv("QUERY_TIMEOUT_SECONDS", "30"))

# Confidence threshold for SQL generation (0.0 - 1.0)
SQL_CONFIDENCE_THRESHOLD = float(os.getenv("SQL_CONFIDENCE_THRESHOLD", "0.6"))

# Maximum rows to return in query results
MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "1000"))

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============================================================================
# VALIDATION & SAFETY
# ============================================================================

# SQL keywords that are always forbidden (write operations)
FORBIDDEN_SQL_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "REPLACE", "WITH RECURSIVE", "EXPLAIN ANALYZE"
}

# Allowed SQL keywords for read operations
ALLOWED_SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER",
    "OUTER", "ON", "GROUP", "BY", "ORDER", "ASC", "DESC", "HAVING",
    "LIMIT", "OFFSET", "WITH", "CASE", "WHEN", "THEN", "ELSE", "END",
    "AND", "OR", "NOT", "DISTINCT", "UNION", "EXCEPT", "INTERSECT"
}
