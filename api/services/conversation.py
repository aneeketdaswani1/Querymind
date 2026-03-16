"""Conversation service for QueryMind API.

Manages conversation state, message history, and orchestrates the agent workflow
for each user query using Redis for state persistence.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import redis.asyncio as redis
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from agent.config import AGENT_DATABASE_URL, ANTHROPIC_API_KEY, REDIS_URL
from agent.core.input_sanitizer import sanitize_user_input
from agent.core.schema_loader import SchemaLoader
from agent.graph.graph import build_agent_graph
from agent.graph.state import QueryMindState, create_initial_state
from api.schemas import (
	ChartPayload,
	DatabaseInfo,
	DatabaseName,
	DatabasesResponse,
	FeedbackRequest,
	FeedbackResponse,
	HealthResponse,
	HistoryItem,
	HistoryResponse,
	InsightPayload,
	QueryRequest,
	QueryResponse,
	QueryStatus,
	SchemaResponse,
)

logger = structlog.get_logger(__name__)


DATABASE_TABLES: Dict[str, List[str]] = {
	"ecommerce": ["customers", "products", "orders", "order_items", "returns"],
	"saas": ["users", "events", "subscriptions", "invoices", "features_usage"],
}


class ConversationService:
	"""Orchestrates query execution and conversation persistence."""

	def __init__(self) -> None:
		self.redis_url = REDIS_URL
		self._redis: Optional[redis.Redis] = None
		self._schema_loader = SchemaLoader(AGENT_DATABASE_URL)
		self._agent = build_agent_graph()
		self._db_engine = create_engine(AGENT_DATABASE_URL, pool_pre_ping=True)
		self.ttl_seconds = 3600
		self.query_rate_limit = 20

	async def startup(self) -> None:
		"""Initialize service connections."""
		self._redis = redis.from_url(self.redis_url, decode_responses=True)
		await self._redis.ping()
		logger.info("conversation_service_started")

	async def shutdown(self) -> None:
		"""Close service connections."""
		if self._redis is not None:
			await self._redis.close()
		self._db_engine.dispose()
		logger.info("conversation_service_stopped")

	async def execute_query(self, request: QueryRequest, client_ip: str) -> QueryResponse:
		"""Process a user query through sanitization, graph execution, and persistence."""
		is_limited = await self._is_rate_limited(client_ip)
		if is_limited:
			return QueryResponse(
				status=QueryStatus.error,
				sql=None,
				sql_explanation="Rate limit exceeded. Max 20 queries/min per IP.",
				results=[],
				row_count=0,
				execution_time_ms=0.0,
				chart=ChartPayload(type="table", config={}),
				insight=InsightPayload(summary="", key_findings=[], suggested_follow_ups=[]),
				clarification_question=None,
				conversation_id=request.conversation_id or str(uuid4()),
			)

		sanitized = sanitize_user_input(request.question)
		conversation_id = request.conversation_id or str(uuid4())

		if not sanitized.is_safe:
			response = QueryResponse(
				status=QueryStatus.error,
				sql=None,
				sql_explanation=sanitized.rejection_reason or "Input rejected",
				results=[],
				row_count=0,
				execution_time_ms=0.0,
				chart=ChartPayload(type="table", config={}),
				insight=InsightPayload(summary="", key_findings=[], suggested_follow_ups=[]),
				clarification_question=None,
				conversation_id=conversation_id,
			)
			await self._append_history(conversation_id, request.question, response)
			return response

		prior_history = await self.get_history(conversation_id)
		messages = self._history_to_messages(prior_history.items)

		state = create_initial_state(
			question=sanitized.cleaned_question,
			active_database=request.database.value,
			messages=messages,
		)
		state_result = await self._agent.ainvoke(state.model_dump())
		final_state = QueryMindState.model_validate(state_result)

		status = QueryStatus.success
		clarification_question = None
		if final_state.needs_clarification or final_state.status == "clarifying":
			status = QueryStatus.clarification
			clarification_question = final_state.clarification_question
		elif final_state.status == "error":
			status = QueryStatus.error

		response = QueryResponse(
			status=status,
			sql=final_state.generated_sql,
			sql_explanation=final_state.sql_explanation or "",
			results=final_state.query_results or [],
			row_count=final_state.row_count,
			execution_time_ms=final_state.execution_time_ms,
			chart=ChartPayload(
				type=final_state.chart_type,
				config=final_state.chart_config or {},
			),
			insight=InsightPayload(
				summary=final_state.insight_text or "",
				key_findings=final_state.key_findings or [],
				suggested_follow_ups=self._suggest_follow_ups(
					sanitized.cleaned_question,
					request.database,
				),
			),
			clarification_question=clarification_question,
			conversation_id=conversation_id,
		)

		await self._append_history(conversation_id, request.question, response)
		return response

	async def get_schema(self, database: DatabaseName) -> SchemaResponse:
		"""Return schema description for selected logical database."""
		schema = self._schema_loader.get_schema_dict()
		selected = DATABASE_TABLES[database.value]
		lines = [f"Database: {database.value}", "", "Tables:"]
		for table in selected:
			if table not in schema:
				continue
			columns = schema[table].get("columns", [])
			col_desc = ", ".join(
				f"{c['name']} ({c['type']})"
				for c in columns
			)
			lines.append(f"- {table}: {col_desc}")

		return SchemaResponse(
			database=database,
			schema_description="\n".join(lines),
		)

	async def get_history(self, conversation_id: str) -> HistoryResponse:
		"""Return conversation history items for a conversation id."""
		key = f"conversation:{conversation_id}:history"
		raw_items = await self._redis.lrange(key, 0, -1) if self._redis else []
		items = [HistoryItem.model_validate_json(item) for item in raw_items]
		return HistoryResponse(conversation_id=conversation_id, items=items)

	async def get_databases(self) -> DatabasesResponse:
		"""List available databases with table counts."""
		schema = self._schema_loader.get_schema_dict()
		databases = []
		for db_name, tables in DATABASE_TABLES.items():
			existing = [t for t in tables if t in schema]
			databases.append(
				DatabaseInfo(
					name=DatabaseName(db_name),
					table_count=len(existing),
					tables=existing,
				)
			)

		return DatabasesResponse(databases=databases)

	async def store_feedback(self, request: FeedbackRequest) -> FeedbackResponse:
		"""Persist user feedback for later evaluation."""
		key = "feedback:items"
		payload = {
			"conversation_id": request.conversation_id,
			"query_id": request.query_id,
			"rating": request.rating,
			"comment": request.comment,
			"timestamp": datetime.now(timezone.utc).isoformat(),
		}
		if self._redis:
			await self._redis.rpush(key, json.dumps(payload))
			await self._redis.expire(key, self.ttl_seconds)
		logger.info("feedback_saved", query_id=request.query_id, rating=request.rating)
		return FeedbackResponse(status="ok")

	async def health(self) -> HealthResponse:
		"""Check connectivity for LLM key, DB, and schema cache availability."""
		llm_status = "connected" if ANTHROPIC_API_KEY else "disconnected"

		db_status = "disconnected"
		try:
			with self._db_engine.connect() as conn:
				conn.execute(text("SELECT 1"))
			db_status = "connected"
		except SQLAlchemyError as exc:
			logger.error("db_health_check_failed", error=str(exc))

		schema_loaded = bool(self._schema_loader.get_schema_dict())

		return HealthResponse(
			status="ok" if db_status == "connected" else "degraded",
			llm=llm_status,
			database=db_status,
			schema_loaded=schema_loaded,
		)

	async def _append_history(
		self,
		conversation_id: str,
		question: str,
		response: QueryResponse,
	) -> None:
		"""Persist one query/response item in Redis conversation history."""
		item = HistoryItem(
			query_id=str(uuid4()),
			timestamp=datetime.now(timezone.utc).isoformat(),
			question=question,
			status=response.status,
			sql=response.sql,
			sql_explanation=response.sql_explanation,
			results=response.results,
			row_count=response.row_count,
			execution_time_ms=response.execution_time_ms,
			chart=response.chart,
			insight=response.insight,
			clarification_question=response.clarification_question,
		)

		if self._redis:
			key = f"conversation:{conversation_id}:history"
			await self._redis.rpush(key, item.model_dump_json())
			await self._redis.expire(key, self.ttl_seconds)

	async def _is_rate_limited(self, client_ip: str) -> bool:
		"""Apply 20 requests/minute sliding-window rate limit per IP."""
		if not self._redis:
			return False

		key = f"ratelimit:{client_ip}"
		now = int(time.time())
		cutoff = now - 60
		member = f"{now}-{uuid4()}"

		pipe = self._redis.pipeline()
		pipe.zremrangebyscore(key, 0, cutoff)
		pipe.zadd(key, {member: now})
		pipe.zcard(key)
		pipe.expire(key, 65)
		_, _, count, _ = await pipe.execute()
		return int(count) > self.query_rate_limit

	def _history_to_messages(self, history_items: List[HistoryItem]) -> List[Dict[str, str]]:
		"""Convert stored history items into graph message format."""
		messages: List[Dict[str, str]] = []
		for item in history_items[-5:]:
			messages.append({"role": "user", "content": item.question})
			assistant_content = item.insight.summary or item.sql_explanation or ""
			if assistant_content:
				messages.append({"role": "assistant", "content": assistant_content})
		return messages

	def _suggest_follow_ups(self, question: str, database: DatabaseName) -> List[str]:
		"""Generate 2-3 natural follow-up questions."""
		if database == DatabaseName.ecommerce:
			return [
				"Can you break this down by month?",
				"Which customer segment contributes the most to this trend?",
				"What changed compared to the previous period?",
			]

		return [
			"Can you segment this by plan tier?",
			"How has this metric changed week over week?",
			"Which features correlate most with this result?",
		]
