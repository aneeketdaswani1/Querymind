"""QueryMind FastAPI application.

Main entry point for the QueryMind API backend. Sets up FastAPI, includes routers,
and configures middleware like CORS.
"""

from __future__ import annotations

import os
import time

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.routers.feedback import router as feedback_router
from api.routers.health import router as health_router
from api.routers.query import router as query_router
from api.routers.schema import router as schema_router
from api.services.conversation import ConversationService

logger = structlog.get_logger(__name__)

FRONTEND_ORIGINS = [
	origin.strip()
	for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
	if origin.strip()
]

app = FastAPI(title="QueryMind API", version="1.0.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=FRONTEND_ORIGINS,
	allow_credentials=True,
	allow_methods=["GET", "POST", "OPTIONS"],
	allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
	"""Structured request/response logging for evaluation."""
	start = time.perf_counter()
	request_body = await request.body()
	body_preview = request_body.decode("utf-8", errors="ignore")[:500]

	logger.info(
		"api_request",
		method=request.method,
		path=request.url.path,
		query=str(request.url.query),
		client_ip=request.client.host if request.client else "unknown",
		body=body_preview,
	)

	response = await call_next(request)
	elapsed_ms = (time.perf_counter() - start) * 1000
	logger.info(
		"api_response",
		method=request.method,
		path=request.url.path,
		status_code=response.status_code,
		elapsed_ms=round(elapsed_ms, 2),
	)
	return response


@app.on_event("startup")
async def on_startup() -> None:
	"""Initialize shared backend services."""
	app.state.conversation_service = ConversationService()
	await app.state.conversation_service.startup()
	logger.info("api_started")


@app.on_event("shutdown")
async def on_shutdown() -> None:
	"""Close shared backend services."""
	await app.state.conversation_service.shutdown()
	logger.info("api_stopped")


app.include_router(query_router)
app.include_router(schema_router)
app.include_router(feedback_router)
app.include_router(health_router)
