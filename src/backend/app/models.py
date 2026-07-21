"""Request/response models for the BuildingAssist API."""

from __future__ import annotations

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
