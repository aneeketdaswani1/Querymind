"""Schema loader module for QueryMind.

Loads and manages database schema information including tables, columns, data types,
and relationships. Provides schema context to the LLM for accurate SQL generation.

The SchemaLoader introspects PostgreSQL databases and provides formatted schema
information optimized for LLM consumption, including table structure, column types,
foreign key relationships, and sample values for categorical columns.
"""

from typing import Optional, Dict, List, Any
from functools import lru_cache
from datetime import datetime
import structlog

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

logger = structlog.get_logger(__name__)


class SchemaLoader:
    """
    Introspects PostgreSQL database schema and provides formatted information for LLM.
    
    Caches schema on first load and provides methods to:
    - Get full schema text formatted for LLM consumption
    - Get sample values for categorical columns
    - Get table relationships via foreign keys
    - Get one-line summary of all tables
    """
    
    def __init__(self, database_url: str):
        """
        Initialize SchemaLoader with database connection URL.
        
        Args:
            database_url: SQLAlchemy-compatible PostgreSQL connection string
                         e.g., postgresql://user:pass@localhost/dbname
        
        Raises:
            SQLAlchemyError: If database connection fails
        """
        self.database_url = database_url
        self.engine: Optional[Engine] = None
        self._schema_cache: Optional[Dict[str, Any]] = None
        self._schema_text_cache: Optional[str] = None
        self._loaded_at: Optional[datetime] = None
        
        logger.info("schema_loader_initialized", database_url=database_url.split("@")[-1])
    
    def _connect(self) -> Engine:
        """Create SQLAlchemy engine if not already connected."""
        if self.engine is None:
            try:
                self.engine = create_engine(
                    self.database_url,
                    echo=False,
                    pool_pre_ping=True,
                    connect_args={"connect_timeout": 10}
                )
                # Test connection
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("database_connected")
            except SQLAlchemyError as e:
                logger.error("database_connection_failed", error=str(e))
                raise
        return self.engine
    
    def _introspect_schema(self) -> Dict[str, Any]:
        """
        Introspect database schema and return structured information.
        
        Returns:
            Dict with table metadata including columns, types, constraints, row counts
        """
        engine = self._connect()
        inspector = inspect(engine)
        
        schema_data = {}
        
        try:
            for table_name in inspector.get_table_names():
                columns_info = []
                
                for column in inspector.get_columns(table_name):
                    col_data = {
                        "name": column["name"],
                        "type": str(column["type"]),
                        "nullable": column["nullable"],
                        "default": column.get("default"),
                        "comment": column.get("comment", ""),
                    }
                    columns_info.append(col_data)
                
                # Get constraints
                pk_constraint = inspector.get_pk_constraint(table_name)
                pk_columns = pk_constraint["constrained_columns"] if pk_constraint else []
                
                fk_constraints = inspector.get_foreign_keys(table_name)
                
                indexes = []
                for idx in inspector.get_indexes(table_name):
                    indexes.append({
                        "name": idx["name"],
                        "columns": idx["column_names"],
                        "unique": idx["unique"],
                    })
                
                # Get row count
                with engine.connect() as conn:
                    result = conn.execute(
                        text(f'SELECT COUNT(*) FROM "{table_name}"')
                    )
                    row_count = result.scalar()
                
                schema_data[table_name] = {
                    "columns": columns_info,
                    "primary_key": pk_columns,
                    "foreign_keys": fk_constraints,
                    "indexes": indexes,
                    "row_count": row_count,
                    "comment": inspector.get_table_comment(table_name).get("text", ""),
                }
            
            self._loaded_at = datetime.now()
            logger.info("schema_introspection_complete", table_count=len(schema_data))
            
        except SQLAlchemyError as e:
            logger.error("schema_introspection_failed", error=str(e))
            raise
        
        return schema_data
    
    def _get_cached_schema(self) -> Dict[str, Any]:
        """Get cached schema or load if not cached."""
        if self._schema_cache is None:
            self._schema_cache = self._introspect_schema()
        return self._schema_cache

    def get_schema_dict(self) -> Dict[str, Any]:
        """Return cached schema metadata as a dictionary."""
        return self._get_cached_schema()
    
    def _format_column_type(self, col_type: str) -> str:
        """Format SQLAlchemy column type for LLM readability."""
        # Simplify complex types
        if "VARCHAR" in col_type.upper():
            return "VARCHAR"
        if "INTEGER" in col_type.upper() or "SERIAL" in col_type.upper():
            return "INTEGER"
        if "DECIMAL" in col_type.upper() or "NUMERIC" in col_type.upper():
            return "DECIMAL"
        if "DATE" in col_type.upper():
            return "DATE"
        if "TIMESTAMP" in col_type.upper():
            return "TIMESTAMP"
        if "BOOLEAN" in col_type.upper():
            return "BOOLEAN"
        if "JSONB" in col_type.upper() or "JSON" in col_type.upper():
            return "JSONB"
        return col_type.upper()
    
    def get_column_samples(
        self, 
        table: str, 
        column: str, 
        limit: int = 20
    ) -> List[Any]:
        """
        Get sample distinct values for a column.
        
        Useful for understanding categorical columns and generating WHERE clauses.
        For columns with < 20 distinct values, returns all distinct values.
        
        Args:
            table: Table name
            column: Column name
            limit: Maximum number of distinct values to return
        
        Returns:
            List of distinct column values, ordered by frequency
        """
        engine = self._connect()
        
        try:
            with engine.connect() as conn:
                query = text(f'''
                    SELECT "{column}", COUNT(*) as count
                    FROM "{table}"
                    GROUP BY "{column}"
                    ORDER BY count DESC
                    LIMIT {limit}
                ''')
                result = conn.execute(query)
                return [row[0] for row in result.fetchall()]
        except SQLAlchemyError as e:
            logger.warning("column_samples_failed", table=table, column=column, error=str(e))
            return []
    
    def get_table_relationships(self) -> Dict[str, List[str]]:
        """
        Get table relationships via foreign keys.
        
        Returns:
            Dict mapping table names to lists of related table names
        """
        schema = self._get_cached_schema()
        relationships: Dict[str, List[str]] = {}
        
        for table_name, table_info in schema.items():
            related_tables = set()
            
            # Foreign keys pointing out from this table
            for fk in table_info.get("foreign_keys", []):
                if fk.get("referred_table"):
                    related_tables.add(fk["referred_table"])
            
            relationships[table_name] = sorted(list(related_tables))
        
        return relationships
    
    def get_schema_summary(self) -> str:
        """
        Get one-line summary of all tables for quick context.
        
        Returns:
            Multi-line string with one summary per table
        """
        schema = self._get_cached_schema()
        lines = []
        
        for table_name in sorted(schema.keys()):
            info = schema[table_name]
            col_count = len(info["columns"])
            row_count = info["row_count"]
            comment = info.get("comment", "")
            
            if comment:
                lines.append(f"{table_name}: {comment} (~{row_count} rows, {col_count} columns)")
            else:
                lines.append(f"{table_name}: ~{row_count} rows, {col_count} columns")
        
        return "\n".join(lines)
    
    def get_schema_text(self) -> str:
        """
        Get full schema formatted for LLM consumption.
        
        Returns formatted schema with:
        - Table and column information
        - Data types and constraints (PRIMARY KEY, NOT NULL, UNIQUE)
        - Foreign key relationships
        - Row counts
        - For VARCHAR columns with < 20 distinct values, includes sample values
        - Column comments if available
        
        Returns:
            Formatted schema string optimized for LLM understanding
        """
        if self._schema_text_cache is not None:
            return self._schema_text_cache
        
        schema = self._get_cached_schema()
        lines = []
        
        lines.append("=" * 80)
        lines.append("DATABASE SCHEMA")
        lines.append("=" * 80)
        lines.append("")
        
        for table_name in sorted(schema.keys()):
            info = schema[table_name]
            
            # Table header
            lines.append(f"TABLE: {table_name}")
            if info.get("comment"):
                lines.append(f"  Description: {info['comment']}")
            
            # Columns
            lines.append("  COLUMNS:")
            for col in info["columns"]:
                col_type = self._format_column_type(col["type"])
                nullable_str = "" if col["nullable"] else ", NOT NULL"
                
                # Check if primary key
                if col["name"] in info.get("primary_key", []):
                    constraint = ", PRIMARY KEY"
                elif col["name"] in [fk["constrained_columns"][0] for fk in info.get("foreign_keys", []) if len(fk.get("constrained_columns", [])) == 1]:
                    # Find which table it references
                    for fk in info.get("foreign_keys", []):
                        if col["name"] in fk.get("constrained_columns", []):
                            constraint = f", FK -> {fk['referred_table']}.{fk['referred_columns'][0]}"
                            break
                else:
                    constraint = ""
                
                line = f"    - {col['name']} ({col_type}{nullable_str}{constraint})"
                
                if col.get("comment"):
                    line += f" -- {col['comment']}"
                
                lines.append(line)
                
                # Add sample values for VARCHAR columns with few distinct values
                if "VARCHAR" in col_type:
                    try:
                        samples = self.get_column_samples(table_name, col["name"], limit=20)
                        if samples and len(samples) <= 20:
                            formatted_samples = [f"'{s}'" if isinstance(s, str) else str(s) for s in samples[:10]]
                            lines.append(f"      Values: [{', '.join(formatted_samples)}]")
                    except Exception as e:
                        logger.debug("sample_values_failed", table=table_name, column=col["name"])
            
            # Foreign keys (if multiple columns or cross-table references)
            if info.get("foreign_keys"):
                lines.append("  FOREIGN KEYS:")
                for fk in info["foreign_keys"]:
                    constrained = ", ".join(fk.get("constrained_columns", []))
                    referred = ", ".join(fk.get("referred_columns", []))
                    lines.append(f"    - ({constrained}) -> {fk['referred_table']}({referred})")
            
            # Row count
            lines.append(f"  ROW COUNT: {info['row_count']:,}")
            
            # Indexes (excluding primary key)
            if info.get("indexes"):
                pk_cols = set(info.get("primary_key", []))
                non_pk_indexes = [
                    idx for idx in info["indexes"] 
                    if set(idx["columns"]) != pk_cols
                ]
                if non_pk_indexes:
                    lines.append("  INDEXES:")
                    for idx in non_pk_indexes:
                        unique_str = " (UNIQUE)" if idx["unique"] else ""
                        cols = ", ".join(idx["columns"])
                        lines.append(f"    - {idx['name']}: ({cols}){unique_str}")
            
            lines.append("")
        
        # Add summary of relationships
        if len(schema) > 1:
            relationships = self.get_table_relationships()
            lines.append("=" * 80)
            lines.append("TABLE RELATIONSHIPS")
            lines.append("=" * 80)
            for table_name in sorted(relationships.keys()):
                if relationships[table_name]:
                    related = ", ".join(relationships[table_name])
                    lines.append(f"{table_name} -> {related}")
            lines.append("")
        
        schema_text = "\n".join(lines)
        self._schema_text_cache = schema_text
        
        logger.info(
            "schema_text_generated",
            table_count=len(schema),
            char_count=len(schema_text),
            cached_at=self._loaded_at
        )
        
        return schema_text
    
    def refresh_schema(self) -> None:
        """
        Explicitly refresh the cached schema.
        
        Call this if database schema changes and you need updated information.
        """
        self._schema_cache = None
        self._schema_text_cache = None
        logger.info("schema_cache_refreshed")
