"""Request/response models for the BuildingAssist API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """A single energy question from the frontend."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        examples=["How much energy did Floor 3 use this week?"],
    )


class Citation(BaseModel):
    """A source citation returned by Foundry IQ grounding."""

    title: str = ""
    url: str = ""
    snippet: str = ""


class AskResponse(BaseModel):
    """The agent's answer plus any grounding citations."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)


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
