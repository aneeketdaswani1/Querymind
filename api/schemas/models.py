"""Pydantic request/response schemas for QueryMind API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DatabaseName(str, Enum):
    ecommerce = "ecommerce"
    saas = "saas"


class QueryStatus(str, Enum):
    success = "success"
    clarification = "clarification"
    error = "error"


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    database: DatabaseName = Field(default=DatabaseName.ecommerce)
    conversation_id: Optional[str] = None


class ChartPayload(BaseModel):
    type: str
    config: Dict[str, Any] = Field(default_factory=dict)


class InsightPayload(BaseModel):
    summary: str = ""
    key_findings: List[str] = Field(default_factory=list)
    suggested_follow_ups: List[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    status: QueryStatus
    sql: Optional[str] = None
    sql_explanation: str = ""
    results: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    chart: ChartPayload
    insight: InsightPayload
    clarification_question: Optional[str] = None
    conversation_id: str


class SchemaResponse(BaseModel):
    database: DatabaseName
    schema_description: str


class HistoryItem(BaseModel):
    query_id: str
    timestamp: str
    question: str
    status: QueryStatus
    sql: Optional[str] = None
    sql_explanation: str = ""
    results: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    chart: ChartPayload
    insight: InsightPayload
    clarification_question: Optional[str] = None


class HistoryResponse(BaseModel):
    conversation_id: str
    items: List[HistoryItem] = Field(default_factory=list)


class DatabaseInfo(BaseModel):
    name: DatabaseName
    table_count: int
    tables: List[str] = Field(default_factory=list)


class DatabasesResponse(BaseModel):
    databases: List[DatabaseInfo] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str = "ok"


class HealthResponse(BaseModel):
    status: str
    llm: str
    database: str
    schema_loaded: bool


class CsvUploadResponse(BaseModel):
    file_name: str
    row_count: int
    column_count: int
    columns: List[str] = Field(default_factory=list)
    preview_rows: List[Dict[str, str]] = Field(default_factory=list)
