"""BuildingAssist API with chat and simulated operations over MCP."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .foundry_client import get_client
from .mcp_server import mcp_http_app, mcp_server
from .models import AskRequest, AskResponse
from .telemetry import configure_tracing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("buildingassist.api")
configure_tracing()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(
    title="BuildingAssist",
    version="0.1.0",
    summary="A minimal Smart Building assistant backed by an Azure AI Foundry agent.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.mount("/mcp", mcp_http_app, name="building-operations-mcp")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness/readiness probe used by Container Apps."""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """Answer a building energy question using the Foundry agent."""
    try:
        answer, citations = get_client().ask(request.question)
    except RuntimeError as exc:
        logger.exception("Foundry agent call failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AskResponse(answer=answer, citations=citations)
