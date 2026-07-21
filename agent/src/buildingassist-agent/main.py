# Copyright (c) Microsoft. All rights reserved.

"""BuildingAssist — Foundry hosted agent (Responses protocol).

Answers Contoso Energy building-energy questions by forwarding user input to a
Foundry model via the Responses API, grounded on the Foundry IQ knowledge
(vector store) provisioned by the main project. Replies stream back through the
Responses protocol.
"""

# Agent revision: 2 (grounded via Foundry IQ file_search).

import asyncio
import logging
import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
    TextResponse,
)
from azure.ai.agentserver.responses.models import (
    MessageContentInputTextContent,
    MessageContentOutputTextContent,
)

logger = logging.getLogger(__name__)

_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
_model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
_knowledge_name = os.environ.get("BUILDINGASSIST_KNOWLEDGE_NAME", "buildingassist-knowledge")

_openai_client = (
    AIProjectClient(endpoint=_endpoint, credential=DefaultAzureCredential())
    .get_openai_client()
)
_responses_client = _openai_client.responses

app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(default_fetch_history_count=20),
)

_SYSTEM_PROMPT = (
    "You are BuildingAssist, an assistant for Contoso Energy's smart buildings. "
    "Answer questions about building energy use concisely and factually. When a "
    "knowledge source is available, ground your answer in it and cite the source. "
    "If you don't have the data, say so plainly."
)

_ROLE_MAP = {
    MessageContentOutputTextContent: "assistant",
    MessageContentInputTextContent: "user",
}


def _resolve_vector_store_id() -> str | None:
    """Find the Foundry IQ knowledge vector store by name (best-effort)."""
    try:
        for store in _openai_client.vector_stores.list():
            if getattr(store, "name", None) == _knowledge_name:
                return store.id
    except Exception as exc:  # noqa: BLE001 - grounding is best-effort
        logger.warning("Could not list vector stores; continuing without grounding: %s", exc)
    return None


# Resolved lazily on first request (and cached) so grounding works without
# depending on container-startup timing / RBAC propagation.
_vector_store_cache: dict[str, str | None] = {}


def _get_vector_store_id() -> str | None:
    if "id" not in _vector_store_cache:
        _vector_store_cache["id"] = _resolve_vector_store_id()
    return _vector_store_cache["id"]


def _build_input(current_input: str, history: list) -> list[dict]:
    """Convert platform history + current message into Responses API input."""
    items = []
    for item in history:
        for content in getattr(item, "content", None) or []:
            role = _ROLE_MAP.get(type(content))
            if role and content.text:
                items.append({"role": role, "content": content.text})
    items.append({"role": "user", "content": current_input})
    return items


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    _cancellation_signal: asyncio.Event,
):
    """Forward user input to the model, grounded on Foundry IQ when available."""
    user_input = await context.get_input_text() or "Hello!"
    history = await context.get_history()
    input_items = _build_input(user_input, history)

    kwargs: dict = {
        "model": _model,
        "instructions": _SYSTEM_PROMPT,
        "input": input_items,
        "store": False,
    }
    vector_store_id = _get_vector_store_id()
    if vector_store_id:
        kwargs["tools"] = [{"type": "file_search", "vector_store_ids": [vector_store_id]}]

    response = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _responses_client.create(**kwargs),
    )

    return TextResponse(context, request, text=response.output_text)


app.run()
