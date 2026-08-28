"""BuildingAssist API with chat and simulated building operations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .building_operations import operations
from .config import settings
from .foundry_client import get_client
from .models import AccessRequest, AskRequest, AskResponse, VisitorCheckInRequest
from .operations_api import router as operations_router
from .telemetry import configure_tracing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("buildingassist.api")
security_logger = logging.getLogger("buildingassist.security")
configure_tracing()


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

app.include_router(operations_router)


@app.exception_handler(ValueError)
async def _invalid_request(_request: Request, exc: ValueError) -> JSONResponse:
    # The operations simulator raises ValueError for invalid inputs; surface them as 400s.
    return JSONResponse(status_code=400, content={"detail": str(exc)})


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


def _run_security_operation(operation: str, call: Callable[[], dict], **context: str) -> dict:
    incident_id = f"SEC-{uuid4().hex[:12].upper()}"
    try:
        return call()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _security_failure(operation, incident_id,
                                exc, **context) from exc


@app.post("/security/access-requests")
def request_access(request: AccessRequest) -> dict:
    """Evaluate a simulated badge or mobile building-access request."""
    return _run_security_operation(
        "access_request",
        lambda: operations.request_access(
            request.building_id,
            request.access_point_id,
            request.credential_id,
            request.method,
        ),
        building_id=request.building_id,
        access_point_id=request.access_point_id,
    )


@app.post("/security/visitors/check-in")
def check_in_visitor(request: VisitorCheckInRequest) -> dict:
    """Check a visitor into a simulated building and issue a temporary pass."""
    return _run_security_operation(
        "visitor_check_in",
        lambda: operations.check_in_visitor(
            request.building_id,
            request.access_point_id,
            request.visitor_name,
            request.visitor_email,
            request.host_name,
            request.purpose,
        ),
        building_id=request.building_id,
        access_point_id=request.access_point_id,
    )
