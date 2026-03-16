"""Utilities to retrieve initialized app services from FastAPI request context."""

from __future__ import annotations

from fastapi import Request

from api.services.conversation import ConversationService


def get_conversation_service(request: Request) -> ConversationService:
    """Get conversation service from app state."""
    return request.app.state.conversation_service
