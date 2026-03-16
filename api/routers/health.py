"""Health router for QueryMind API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas import HealthResponse
from api.services.app_context import get_conversation_service
from api.services.conversation import ConversationService

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    service: ConversationService = Depends(get_conversation_service),
) -> HealthResponse:
    """Return backend health and dependency status."""
    return await service.health()
