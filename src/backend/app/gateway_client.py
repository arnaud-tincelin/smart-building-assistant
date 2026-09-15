"""Direct model calls routed through the APIM AI Gateway.

This is the governed lane: the request carries a gateway runtime key instead of a
Foundry credential, and the gateway applies its policies (content safety, token
rate limit, fallback) before the model is ever reached.

It does not use the Foundry Agent Service. The backend orchestrates a bounded
chat-completions loop with read-only building tools through the gateway's MCP endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from functools import lru_cache
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams
from pydantic import ValidationError

from .agent_policy import READ_ONLY_MCP_TOOLS
from .config import settings
from .execution import describe_execution
from .models import AskResponse, TokenUsage

logger = logging.getLogger("buildingassist.gateway")

# The gateway returns 403 for a content safety block and 429 when a rate limit trips.
# Note this is 403, not the 400 the preview documentation states.
CONTENT_SAFETY_STATUS = 403
RATE_LIMITED_STATUS = 429
MAX_TOOL_ROUNDS = 6
MAX_TOOL_CALLS = 12
MAX_DISCOVERY_PAGES = 10
REQUEST_TIMEOUT_SECONDS = 120


class GatewayError(RuntimeError):
    """Raised when the governed model call cannot be completed.

    ``status`` is what the API should return to the caller. Policy blocks are a correct
    outcome, so they must stay out of the 5xx range that the SRE alert watches.
    """

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def _gateway_error(exc: BaseException) -> GatewayError | None:
    if isinstance(exc, GatewayError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for nested in exc.exceptions:
            if error := _gateway_error(nested):
                return error
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == RATE_LIMITED_STATUS:
            retry_after = exc.response.headers.get("Retry-After")
            suffix = f" Retry after {retry_after}s." if retry_after else ""
            return GatewayError(f"AI Gateway MCP rate limit reached.{suffix}", status=status)
        if status in (401, 403):
            return GatewayError(
                "AI Gateway denied access to the building MCP tools.", status=status
            )
    return None


@asynccontextmanager
async def open_tool_session(endpoint: str, api_key: str) -> AsyncGenerator[ClientSession]:
    try:
        async with (
            httpx.AsyncClient(headers={"Api-Key": api_key}, timeout=30) as http_client,
            streamable_http_client(endpoint, http_client=http_client) as (reader, writer, _),
            ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as session,
        ):
            await session.initialize()
            yield session
    except Exception as exc:
        if error := _gateway_error(exc):
            raise error from exc
        logger.warning("AI Gateway MCP session failed (%s).", type(exc).__name__)
        raise GatewayError("Could not complete the AI Gateway building tool request.") from exc


class GatewayModelClient:
    """Minimal OpenAI-compatible chat client pointed at the AI Gateway."""

    def __init__(
        self, endpoint: str, api_key: str, model: str, mcp_server_url: str = ""
    ) -> None:
        self._url = f"{endpoint.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._mcp_server_url = mcp_server_url

    def ask(self, question: str) -> AskResponse:
        return asyncio.run(self._ask(question))

    async def _ask(self, question: str) -> AskResponse:
        started_at = perf_counter()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": settings.gateway_instructions},
            {"role": "user", "content": question},
        ]
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                if not self._mcp_server_url:
                    return await self._run_loop(messages, {}, None, started_at)
                async with open_tool_session(self._mcp_server_url, self._api_key) as session:
                    tools = {}
                    cursor = None
                    for _ in range(MAX_DISCOVERY_PAGES):
                        page = await session.list_tools(
                            params=PaginatedRequestParams(cursor=cursor) if cursor else None
                        )
                        tools.update({
                            tool.name: {
                                "type": "function",
                                "function": {
                                    "name": tool.name,
                                    "description": tool.description or "",
                                    "parameters": tool.inputSchema,
                                },
                            }
                            for tool in page.tools if tool.name in READ_ONLY_MCP_TOOLS
                        })
                        cursor = page.nextCursor
                        if not cursor:
                            break
                    else:
                        raise GatewayError("AI Gateway tool discovery exceeded its page limit.")
                    if not tools:
                        raise GatewayError("AI Gateway returned no approved building tools.")
                    return await self._run_loop(messages, tools, session, started_at)
        except TimeoutError as exc:
            raise GatewayError("AI Gateway request timed out.", status=504) from exc

    async def _run_loop(
        self,
        messages: list[dict[str, Any]],
        tools: dict[str, dict[str, Any]],
        session: ClientSession | None,
        started_at: float,
    ) -> AskResponse:
        tools_used: list[str] = []
        call_count = 0
        usage: TokenUsage | None = TokenUsage.model_validate({
            field: 0 for field in TokenUsage.model_fields
        })
        for round_index in range(MAX_TOOL_ROUNDS + 1):
            body: dict[str, Any] = {"model": self._model, "messages": messages}
            if tools:
                body["tools"] = list(tools.values())
                body["tool_choice"] = "none" if round_index == MAX_TOOL_ROUNDS else "auto"
            payload, headers = await asyncio.to_thread(self._complete, body)
            latency_ms = round((perf_counter() - started_at) * 1000)
            response = self._to_response(payload, headers, latency_ms)
            execution = response.execution
            if execution is None or execution.usage is None:
                usage = None
            elif usage is not None:
                counts = {}
                for field, value in execution.usage.model_dump().items():
                    previous = getattr(usage, field)
                    counts[field] = (
                        previous + value if previous is not None and value is not None else None
                    )
                usage = TokenUsage.model_validate(counts)
            message = ((payload.get("choices") or [{}])[0].get("message") or {})
            calls = message.get("tool_calls") or []
            if not calls:
                if not response.answer:
                    raise GatewayError("AI Gateway returned no answer. Please retry.")
                if execution is not None:
                    execution.usage = usage
                    execution.tools_used = tools_used
                    execution.routing_explanation += (
                        f" The backend made {round_index + 1} model call(s) and {call_count} "
                        "read-only MCP tool call(s) through AI Gateway. "
                        "When available, token totals cover every call; "
                        "model attribution comes from the final response."
                    )
                return response
            if round_index == MAX_TOOL_ROUNDS or call_count + len(calls) > MAX_TOOL_CALLS:
                raise GatewayError("AI Gateway tool-call limit reached. Narrow your question.")
            messages.append({"role": "assistant", "content": message.get("content"),
                             "tool_calls": calls})
            for call in calls:
                function = call.get("function") or {}
                name = function.get("name")
                if session is None or name not in tools or call.get("type") != "function":
                    raise GatewayError("The model requested a tool that is not allowed.")
                if not isinstance(call.get("id"), str) or not call["id"]:
                    raise GatewayError("The model returned an invalid tool call ID.")
                try:
                    arguments = json.loads(function.get("arguments", ""))
                except (TypeError, ValueError) as exc:
                    raise GatewayError("The model returned invalid tool arguments.") from exc
                if not isinstance(arguments, dict):
                    raise GatewayError("The model returned invalid tool arguments.")
                tool_result = await session.call_tool(name, arguments)
                call_count += 1
                if tool_result.isError:
                    raise GatewayError(f"AI Gateway building tool {name} failed.")
                if name not in tools_used:
                    tools_used.append(name)
                messages.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "content": json.dumps(tool_result.model_dump(mode="json", exclude_none=True)),
                })
        raise GatewayError("AI Gateway tool-call limit reached.")

    def _complete(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        request = Request(
            self._url,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Api-Key": self._api_key, "Content-Type": "application/json"},
        )

        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed gateway host
                payload = json.loads(response.read())
                headers = {name.lower(): value for name, value in response.headers.items()}
        except HTTPError as exc:
            raise self._translate(exc) from exc
        except (URLError, TimeoutError) as exc:
            raise GatewayError("Could not reach the AI Gateway.") from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise GatewayError("AI Gateway returned an invalid model response.") from exc
        if not isinstance(payload, dict):
            raise GatewayError("AI Gateway returned an invalid model response.")
        return payload, headers

    @staticmethod
    def _translate(exc: HTTPError) -> GatewayError:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.status == CONTENT_SAFETY_STATUS:
            logger.info("AI Gateway rejected a model request with 403.")
            return GatewayError(
                "AI Gateway rejected the request under its access or content safety policy.",
                status=CONTENT_SAFETY_STATUS,
            )
        if exc.status == RATE_LIMITED_STATUS:
            retry_after = exc.headers.get("Retry-After", "")
            suffix = f" Retry after {retry_after}s." if retry_after else ""
            return GatewayError(
                f"AI Gateway rate limit reached.{suffix}", status=RATE_LIMITED_STATUS
            )
        logger.error("AI Gateway returned %s: %s", exc.status, detail)
        return GatewayError(f"AI Gateway returned {exc.status}.")

    def _to_response(
        self, payload: dict[str, Any], headers: dict[str, str], latency_ms: int,
    ) -> AskResponse:
        choices = payload.get("choices") or []
        if not choices or not isinstance(choices, list) or not isinstance(choices[0], dict):
            raise GatewayError("AI Gateway returned an invalid model response.")
        if choices[0].get("finish_reason") in ("length", "content_filter"):
            raise GatewayError(
                "AI Gateway returned an incomplete or filtered answer. Please retry."
            )
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise GatewayError("AI Gateway returned an invalid model response.")
        content = message.get("content") or ""
        if not isinstance(content, str):
            raise GatewayError("AI Gateway returned an invalid answer.")
        answer = content.strip()

        usage_payload = payload.get("usage")
        usage = None
        if usage_payload is not None and not isinstance(usage_payload, dict):
            raise GatewayError("AI Gateway returned invalid token usage.")
        if isinstance(usage_payload, dict):
            input_details = usage_payload.get("prompt_tokens_details") or {}
            output_details = usage_payload.get("completion_tokens_details") or {}
            if not isinstance(input_details, dict) or not isinstance(output_details, dict):
                raise GatewayError("AI Gateway returned invalid token usage details.")
            try:
                usage = TokenUsage(
                    input_tokens=usage_payload.get("prompt_tokens"),
                    output_tokens=usage_payload.get("completion_tokens"),
                    total_tokens=usage_payload.get("total_tokens"),
                    reasoning_tokens=output_details.get("reasoning_tokens"),
                    cached_tokens=input_details.get("cached_tokens"),
                    cache_write_tokens=input_details.get("cache_write_tokens"),
                )
            except ValidationError as exc:
                raise GatewayError("AI Gateway returned invalid token usage.") from exc

        reported_model = payload.get("model")
        if reported_model is not None and not isinstance(reported_model, str):
            raise GatewayError("AI Gateway returned an invalid model identifier.")
        execution = describe_execution(
            mode="gateway",
            requested_model=self._model,
            reported_model=reported_model,
            routing_mode=None,
            latency_ms=latency_ms,
            response_id=payload.get("id"),
            usage=usage,
            tools_used=[],
        )

        remaining = headers.get("x-ratelimit-remaining-tokens")
        limit = headers.get("x-ratelimit-limit-tokens")
        if remaining and limit:
            execution.routing_explanation += (
                f" Token budget remaining this minute: {remaining} of {limit}."
            )

        return AskResponse(
            answer=answer,
            citations=[],
            execution=execution,
        )


@lru_cache(maxsize=1)
def get_gateway_client() -> GatewayModelClient:
    """Return the shared gateway client, or raise when the lane is not configured."""
    if not (settings.gateway_model_endpoint and settings.gateway_api_key):
        raise GatewayError(
            "The governed lane needs BUILDINGASSIST_GATEWAY_MODEL_ENDPOINT and "
            "BUILDINGASSIST_GATEWAY_API_KEY."
        )
    return GatewayModelClient(
        settings.gateway_model_endpoint,
        settings.gateway_api_key,
        settings.gateway_model,
        mcp_server_url=settings.mcp_server_url,
    )
