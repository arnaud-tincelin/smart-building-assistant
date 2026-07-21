"""BuildingAssist FastAPI application.

A deliberately thin backend: one health probe and one ``/ask`` endpoint that
forwards an energy question to the Azure AI Foundry agent. Everything
interesting in the demo happens *around* the app (the agents at each lifecycle
stage), not inside it.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .foundry_client import get_client
from .models import AskRequest, AskResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("buildingassist.api")

app = FastAPI(
    title="BuildingAssist",
    version="0.1.0",
    summary="A minimal Smart Building assistant backed by an Azure AI Foundry agent.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
