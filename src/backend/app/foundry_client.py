"""Azure AI Foundry client.

The agent the app calls is the combination of a **model deployment**, its
**instructions**, and a **Foundry IQ knowledge** source (a vector store of the
sample building/energy docs). We talk to it through the Foundry project's
OpenAI-compatible **Responses API** with the ``file_search`` tool, which returns a
grounded answer plus file citations.

Authentication uses ``DefaultAzureCredential`` so the same code works locally
(developer login / ``azd``) and in Azure (user-assigned managed identity).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from azure.identity import DefaultAzureCredential

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
        self._openai_client = None
        self._vector_store_id: str | None = None
        self._resolved = False

    def _client(self):
        """Lazily construct the OpenAI-compatible client (needs network + creds)."""
        if self._openai_client is not None:
            return self._openai_client

        from azure.ai.projects import AIProjectClient

        credential_kwargs = {}
        if settings.azure_client_id:
            credential_kwargs["managed_identity_client_id"] = settings.azure_client_id

        credential = DefaultAzureCredential(**credential_kwargs)
        project = AIProjectClient(
            endpoint=settings.project_endpoint, credential=credential
        )
        self._openai_client = project.get_openai_client()
        return self._openai_client

    def _vector_store(self, oai) -> str | None:
        """Resolve the Foundry IQ knowledge vector store id by name (cached)."""
        if self._resolved:
            return self._vector_store_id

        self._resolved = True
        try:
            for store in oai.vector_stores.list():
                if getattr(store, "name", None) == settings.knowledge_name:
                    self._vector_store_id = store.id
                    break
        except Exception:  # noqa: BLE001 - grounding is best-effort
            logger.warning("Could not list vector stores; continuing without grounding.")
        if self._vector_store_id is None:
            logger.info("No knowledge vector store %r found.", settings.knowledge_name)
        return self._vector_store_id

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
        vector_store_id = self._vector_store(oai)

        kwargs: dict = {
            "model": settings.model_deployment,
            "instructions": settings.instructions,
            "input": question,
        }
        if vector_store_id:
            kwargs["tools"] = [
                {"type": "file_search", "vector_store_ids": [vector_store_id]}
            ]
            kwargs["include"] = ["file_search_call.results"]

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
        """Build citations from inline annotations and file_search retrieval results."""
        citations: list[Citation] = []
        seen: set[str] = set()

        def add(title: str, url: str, snippet: str) -> None:
            key = url or title
            if not key or key in seen:
                return
            seen.add(key)
            citations.append(Citation(title=title, url=url, snippet=snippet))

        for item in getattr(response, "output", None) or []:
            item_type = getattr(item, "type", None)

            # Inline citations the model emits in its answer.
            for content in getattr(item, "content", None) or []:
                for ann in getattr(content, "annotations", None) or []:
                    add(
                        getattr(ann, "filename", None) or getattr(ann, "title", None) or "",
                        getattr(ann, "url", "") or "",
                        "",
                    )

            # The documents the file_search tool actually retrieved.
            if item_type == "file_search_call":
                for result in getattr(item, "results", None) or []:
                    text = (getattr(result, "text", None) or "").strip().replace("\n", " ")
                    add(getattr(result, "filename", None) or "", "", text[:160])

        return citations


@lru_cache(maxsize=1)
def get_client() -> FoundryAgentClient:
    """Return a process-wide singleton client."""
    return FoundryAgentClient()
