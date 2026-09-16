"""Request/response models for the BuildingAssist API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AskMode = Literal["agents", "gateway"]
RoutingMode = Literal["balanced", "cost", "quality"]


class AskRequest(BaseModel):
    """A single energy question from the frontend."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        examples=["How much energy did Floor 3 use this week?"],
    )
    mode: AskMode = "agents"


class Citation(BaseModel):
    """A source citation returned by Foundry IQ grounding."""

    title: str = ""
    url: str = ""
    snippet: str = ""


class TokenUsage(BaseModel):
    """Reported token counts; missing measurements remain unknown, not zero."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)


class ModelExecution(BaseModel):
    """Execution facts returned by the service, separate from router configuration."""

    mode: AskMode
    requested_model: str
    reported_model: str | None = None
    selected_model: str | None = None
    routing_mode: RoutingMode | None = None
    latency_ms: int = Field(ge=0)
    response_id: str | None = None
    usage: TokenUsage | None = None
    tools_used: list[str] = Field(default_factory=list)
    routing_explanation: str


class AskResponse(BaseModel):
    """The answer, grounding citations, and optional execution measurements."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    execution: ModelExecution | None = None


class RoutingModeRequest(BaseModel):
    mode: RoutingMode


class RoutingModeState(BaseModel):
    mode: RoutingMode
    editable: bool
    explicitly_set: bool
    model_name: str
    model_version: str
    model_subset: list[str] = Field(default_factory=list)
    propagation_seconds: int = 300


class AccessRequest(BaseModel):
    """A badge or mobile credential presented at a building access point."""

    building_id: str = Field(..., min_length=1, max_length=64)
    access_point_id: str = Field(..., min_length=1, max_length=64)
    credential_id: str = Field(..., min_length=1, max_length=64)
    method: Literal["badge", "mobile"]


class VisitorCheckInRequest(BaseModel):
    """A visitor arrival that requires a temporary building pass."""

    building_id: str = Field(..., min_length=1, max_length=64)
    access_point_id: str = Field(..., min_length=1, max_length=64)
    visitor_name: str = Field(..., min_length=1, max_length=120)
    visitor_email: str = Field(..., min_length=3, max_length=254)
    host_name: str = Field(..., min_length=1, max_length=120)
    purpose: str = Field(..., min_length=1, max_length=240)


class WorkOrderRequest(BaseModel):
    """A fictional maintenance work order requested through the operations API."""

    building_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=160)
    reason: str = Field(..., min_length=1, max_length=500)
    priority: Literal["low", "medium", "high"] = "medium"


class HvacSetpointRequest(BaseModel):
    """A temporary fictional HVAC setpoint requested through the operations API."""

    building_id: str = Field(..., min_length=1, max_length=64)
    zone_id: str = Field(..., min_length=1, max_length=64)
    temperature_c: float
    duration_minutes: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=500)
    confirmed: bool = False
