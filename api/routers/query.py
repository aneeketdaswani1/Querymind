"""Query execution router for QueryMind API.

Handles endpoints for natural language query submission, result retrieval, and
progress tracking through the agent workflow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.schemas import HistoryResponse, QueryRequest, QueryResponse
from api.services.app_context import get_conversation_service
from api.services.conversation import ConversationService

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_data(
	payload: QueryRequest,
	request: Request,
	service: ConversationService = Depends(get_conversation_service),
) -> QueryResponse:
	"""Execute a natural-language query against selected database context."""
	client_ip = request.client.host if request.client else "unknown"
	return await service.execute_query(payload, client_ip)


@router.get("/history/{conversation_id}", response_model=HistoryResponse)
async def get_history(
	conversation_id: str,
	service: ConversationService = Depends(get_conversation_service),
) -> HistoryResponse:
	"""Return all query/response items for a conversation."""
	return await service.get_history(conversation_id)
