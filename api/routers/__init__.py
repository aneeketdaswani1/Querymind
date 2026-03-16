"""API router exports."""

from api.routers.feedback import router as feedback_router
from api.routers.health import router as health_router
from api.routers.query import router as query_router
from api.routers.schema import router as schema_router

__all__ = [
	"feedback_router",
	"health_router",
	"query_router",
	"schema_router",
]
"""API routers package for QueryMind.

Contains route handlers organized by feature: query execution, schema retrieval, and feedback.
"""
