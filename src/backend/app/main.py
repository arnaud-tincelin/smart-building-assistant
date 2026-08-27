"""BuildingAssist API with chat and simulated operations over MCP."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .building_operations import operations
from .config import settings
from .foundry_client import get_client
from .mcp_server import mcp_http_app, mcp_server
from .models import AccessRequest, AskRequest, AskResponse, VisitorCheckInRequest
from .telemetry import configure_tracing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("buildingassist.api")
security_logger = logging.getLogger("buildingassist.security")
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


def _security_failure(
    operation: str,
    incident_id: str,
    error: Exception,
    **context: str,
) -> HTTPException:
    security_logger.error(
        "Security control operation failed: incident_id=%s operation=%s",
        incident_id,
        operation,
        exc_info=error,
        extra={"operation": operation, "incident_id": incident_id, **context},
    )
    return HTTPException(
        status_code=500,
        detail={
            "code": "security_control_failure",
            "message": "The building access service could not complete the request.",
            "operation": operation,
            "incident_id": incident_id,
        },
        headers={"X-Incident-ID": incident_id},
    )


@app.post("/security/access-requests")
def request_access(request: AccessRequest) -> dict:
    """Evaluate a simulated badge or mobile building-access request."""
    incident_id = f"SEC-{uuid4().hex[:12].upper()}"
    try:
        return operations.request_access(
            request.building_id,
            request.access_point_id,
            request.credential_id,
            request.method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _security_failure(
            "access_request",
            incident_id,
            exc,
            building_id=request.building_id,
            access_point_id=request.access_point_id,
        ) from exc


@app.post("/security/visitors/check-in")
def check_in_visitor(request: VisitorCheckInRequest) -> dict:
    """Check a visitor into a simulated building and issue a temporary pass."""
    incident_id = f"SEC-{uuid4().hex[:12].upper()}"
    try:
        return operations.check_in_visitor(
            request.building_id,
            request.access_point_id,
            request.visitor_name,
            request.visitor_email,
            request.host_name,
            request.purpose,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _security_failure(
            "visitor_check_in",
            incident_id,
            exc,
            building_id=request.building_id,
            access_point_id=request.access_point_id,
        ) from exc
