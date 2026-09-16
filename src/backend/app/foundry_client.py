"""Azure AI Foundry client.

The agent the app calls is the combination of a **model deployment**, its
**instructions**, a **Foundry IQ knowledge** source, and live-like data exposed by
the simulated building-operations **MCP** server. We call it through the Foundry
project's OpenAI-compatible **Responses API**.

Authentication uses ``DefaultAzureCredential`` so the same code works locally
(developer login / ``azd``) and in Azure (user-assigned managed identity).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from time import perf_counter

from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAIError, RateLimitError

from .agent_policy import READ_ONLY_MCP_TOOLS
from .config import settings
from .execution import describe_execution
from .model_router import known_mode
from .models import AskResponse, Citation, TokenUsage
from .telemetry import record_agent_execution, trace_agent_call

logger = logging.getLogger("buildingassist.foundry")

_MOCK_ANSWER = (
    "Floor 3 used approximately 1,240 kWh this week — about 8% higher than last "
    "week, driven mostly by HVAC load during the warm afternoons."
)
_MOCK_CITATIONS = [
    Citation(
        title="Contoso Energy — Floor 3 metering export (sample)",
        url="",
        snippet="Weekly submeter totals for Floor 3 lighting, HVAC and plug loads.",
    )
]

class FoundryRateLimitError(RuntimeError):
    def __init__(self, retry_after: str | None) -> None:
        message = "The Foundry model is busy or rate-limited."
        if retry_after and retry_after.isdecimal():
            message += f" Retry after {retry_after}s."
        else:
            message += " Please retry shortly."
        super().__init__(message)
        self.retry_after = retry_after


class FoundryAgentClient:
    """Small facade over the Foundry project's Responses API."""

    def __init__(self) -> None:
        self._project_client = None
        self._openai_client = None
        self._credential = None
        self._search_token_provider = None
        self._agent_id: str | None = None

    def _default_credential(self):
        if self._credential is None:
            credential_kwargs = {}
            if settings.azure_client_id:
                credential_kwargs["managed_identity_client_id"] = settings.azure_client_id
            self._credential = DefaultAzureCredential(**credential_kwargs)
        return self._credential

    def _project(self):
        """Lazily construct the Foundry project client."""
        if self._project_client is not None:
            return self._project_client
        from azure.ai.projects import AIProjectClient

        self._project_client = AIProjectClient(
            endpoint=settings.project_endpoint, credential=self._default_credential()
        )
        return self._project_client

    def _client(self):
        """Lazily construct the OpenAI-compatible client (needs network + creds)."""
        if self._openai_client is not None:
            return self._openai_client

        self._openai_client = self._project().get_openai_client()
        return self._openai_client

    def _agent_reference(self) -> dict[str, str]:
        if self._agent_id is None:
            agent = self._project().agents.get(settings.agent_name)
            self._agent_id = agent.id
        return {
            "name": settings.agent_name,
            "id": self._agent_id,
            "type": "agent_reference",
        }

    def _search_token(self) -> str:
        if self._search_token_provider is None:
            self._search_token_provider = get_bearer_token_provider(
                self._default_credential(), "https://search.azure.com/.default"
            )
        return self._search_token_provider()

    def ask(self, question: str) -> AskResponse:
        """Invoke the single configured agent and retain its response metadata."""
        if settings.use_mock_agent:
            logger.info("Mock agent enabled — returning canned answer.")
            return AskResponse(answer=_MOCK_ANSWER, citations=list(_MOCK_CITATIONS))

        if not settings.project_endpoint:
            raise RuntimeError(
                "Foundry is not configured. Set BUILDINGASSIST_PROJECT_ENDPOINT, or "
                "enable BUILDINGASSIST_USE_MOCK_AGENT=true."
            )

        try:
            return self._ask(question)
        except RateLimitError as exc:
            retry_after = exc.response.headers.get("retry-after")
            logger.warning("Foundry model rate-limited the request; retry-after=%s", retry_after)
            raise FoundryRateLimitError(retry_after) from exc
        except (AzureError, OpenAIError) as exc:
            logger.exception("Foundry request failed")
            raise RuntimeError("The Foundry agent request failed. Check the backend logs.") from exc

    def _ask(self, question: str) -> AskResponse:
        oai = self._client()
        kwargs: dict
        if settings.agent_name:
            kwargs = {
                "input": question,
                "extra_body": {
                    "agent_reference": self._agent_reference(),
                },
            }
            return self._create_response(oai, kwargs)

        kwargs = {
            "model": settings.model_deployment,
            "instructions": settings.instructions,
            "input": question,
        }
        if settings.knowledge_mcp_endpoint:
            kwargs.setdefault("tools", []).append(
                {
                    "type": "mcp",
                    "server_label": "building_knowledge",
                    "server_description": (
                        "Foundry IQ Knowledge Base for stable Contoso building facts."
                    ),
                    "server_url": settings.knowledge_mcp_endpoint,
                    "allowed_tools": ["knowledge_base_retrieve"],
                    "headers": {"Authorization": f"Bearer {self._search_token()}"},
                    "require_approval": "never",
                }
            )
        if settings.mcp_server_url:
            operations_tool = {
                "type": "mcp",
                "server_label": "building_operations",
                "server_description": (
                    "Fictional current telemetry and alerts for Contoso buildings."
                ),
                "server_url": settings.mcp_server_url,
                "allowed_tools": READ_ONLY_MCP_TOOLS,
                "require_approval": "never",
            }
            if settings.gateway_api_key:
                operations_tool["headers"] = {"Api-Key": settings.gateway_api_key}
            kwargs.setdefault("tools", []).append(operations_tool)

        return self._create_response(oai, kwargs)

    def _create_response(self, oai, kwargs: dict) -> AskResponse:
        with trace_agent_call() as (span, headers):
            if headers:
                kwargs = {
                    **kwargs,
                    "extra_headers": {**(kwargs.get("extra_headers") or {}), **headers},
                }
            result = self._invoke_response(oai, kwargs)
            if result.execution is not None:
                record_agent_execution(span, result.execution)
            return result

    def _invoke_response(self, oai, kwargs: dict) -> AskResponse:
        routing_mode = known_mode()
        started_at = perf_counter()
        response = oai.responses.create(**kwargs)
        latency_ms = round((perf_counter() - started_at) * 1000)
        status = getattr(response, "status", None)
        if status and status != "completed":
            logger.error("Foundry response %s has status %s", getattr(response, "id", ""), status)
            raise RuntimeError(f"The Foundry agent response was {status}. Please retry.")

        answer = (getattr(response, "output_text", None) or "").strip()
        citations = self._extract_citations(response)
        if not answer:
            raise RuntimeError("The Foundry agent did not return an answer.")

        raw_usage = getattr(response, "usage", None)
        usage = None
        if raw_usage is not None:
            usage = TokenUsage(
                input_tokens=getattr(raw_usage, "input_tokens", None),
                output_tokens=getattr(raw_usage, "output_tokens", None),
                total_tokens=getattr(raw_usage, "total_tokens", None),
                reasoning_tokens=getattr(
                    getattr(raw_usage, "output_tokens_details", None), "reasoning_tokens", None
                ),
                cached_tokens=getattr(
                    getattr(raw_usage, "input_tokens_details", None), "cached_tokens", None
                ),
                cache_write_tokens=getattr(
                    getattr(raw_usage, "input_tokens_details", None), "cache_write_tokens", None
                ),
            )
        tools_used = list(dict.fromkeys(
            item.name
            for item in getattr(response, "output", None) or []
            if getattr(item, "type", None) in ("mcp_call", "function_call")
            and getattr(item, "name", None)
        ))
        execution = describe_execution(
            mode="agents",
            requested_model=settings.model_deployment,
            reported_model=getattr(response, "model", None),
            routing_mode=routing_mode,
            latency_ms=latency_ms,
            response_id=getattr(response, "id", None),
            usage=usage,
            tools_used=tools_used,
        )
        return AskResponse(answer=answer, citations=citations, execution=execution)

    @staticmethod
    def _extract_citations(response) -> list[Citation]:
        """Build citations from inline response annotations."""
        citations: list[Citation] = []
        seen: set[str] = set()

        def add(title: str, url: str, snippet: str) -> None:
            key = url or title
            if not key or key in seen:
                return
            seen.add(key)
            citations.append(Citation(title=title, url=url, snippet=snippet))

        for item in getattr(response, "output", None) or []:
            for content in getattr(item, "content", None) or []:
                for ann in getattr(content, "annotations", None) or []:
                    add(
                        getattr(ann, "filename", None) or getattr(
                            ann, "title", None) or "",
                        getattr(ann, "url", "") or "",
                        "",
                    )

        return citations


@lru_cache(maxsize=1)
def get_client() -> FoundryAgentClient:
    """Return a process-wide singleton client."""
    return FoundryAgentClient()
