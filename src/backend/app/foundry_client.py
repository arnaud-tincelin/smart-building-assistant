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

from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from .agent_policy import READ_ONLY_MCP_TOOLS
from .config import settings
from .models import Citation

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

    def ask(self, question: str) -> tuple[str, list[Citation]]:
        """Ask the Foundry agent a question and return (answer, citations)."""
        if settings.use_mock_agent:
            logger.info("Mock agent enabled — returning canned answer.")
            return _MOCK_ANSWER, list(_MOCK_CITATIONS)

        if not settings.project_endpoint:
            raise RuntimeError(
                "Foundry is not configured. Set BUILDINGASSIST_PROJECT_ENDPOINT, or "
                "enable BUILDINGASSIST_USE_MOCK_AGENT=true."
            )

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
            kwargs.setdefault("tools", []).append(
                {
                    "type": "mcp",
                    "server_label": "building_operations",
                    "server_description": (
                        "Fictional current telemetry and alerts for Contoso buildings."
                    ),
                    "server_url": settings.mcp_server_url,
                    "allowed_tools": READ_ONLY_MCP_TOOLS,
                    "require_approval": "never",
                }
            )

        return self._create_response(oai, kwargs)

    def _create_response(self, oai, kwargs: dict) -> tuple[str, list[Citation]]:
        try:
            response = oai.responses.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface as a clean 502
            raise RuntimeError(f"Foundry request failed: {exc}") from exc

        answer = (getattr(response, "output_text", None) or "").strip()
        citations = self._extract_citations(response)
        if not answer:
            answer = "The agent did not return an answer."
        return answer, citations

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
