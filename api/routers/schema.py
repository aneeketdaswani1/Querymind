"""Database schema router for QueryMind API.

Provides endpoints for retrieving database schema information including tables,
columns, and relationships used by the frontend for context and autocomplete.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas import DatabaseName, DatabasesResponse, SchemaResponse
from api.services.app_context import get_conversation_service
from api.services.conversation import ConversationService

router = APIRouter(prefix="/api/v1", tags=["schema"])


@router.get("/schema/{database}", response_model=SchemaResponse)
async def get_schema(
	database: DatabaseName,
	service: ConversationService = Depends(get_conversation_service),
) -> SchemaResponse:
	"""Return schema description for one logical dataset."""
	return await service.get_schema(database)


@router.get("/databases", response_model=DatabasesResponse)
async def list_databases(
	service: ConversationService = Depends(get_conversation_service),
) -> DatabasesResponse:
	"""List available logical databases and table counts."""
	return await service.get_databases()
