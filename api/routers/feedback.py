"""Feedback router for QueryMind API.

Handles endpoints for collecting user feedback on generated queries and insights
for continuous improvement of the agent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas import FeedbackRequest, FeedbackResponse
from api.services.app_context import get_conversation_service
from api.services.conversation import ConversationService

router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
	payload: FeedbackRequest,
	service: ConversationService = Depends(get_conversation_service),
) -> FeedbackResponse:
	"""Store user rating/comment for one query result."""
	return await service.store_feedback(payload)
