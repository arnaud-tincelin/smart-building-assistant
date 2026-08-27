from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import settings
from app.foundry_client import FoundryAgentClient
from app.mcp_server import READ_ONLY_TOOLS


class _FakeResponses:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.kwargs = kwargs
        return SimpleNamespace(output_text="Simulated current data.", output=[])


def test_foundry_request_invokes_the_prompt_agent_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = _FakeResponses()
    client = FoundryAgentClient()
    client._openai_client = SimpleNamespace(responses=responses)
    client._project_client = SimpleNamespace(
        agents=SimpleNamespace(
            get=lambda _name: SimpleNamespace(
                id="agent-resource-id",
                name="buildingassist-agent",
            )
        )
    )

    monkeypatch.setattr(settings, "use_mock_agent", False)
    monkeypatch.setattr(settings, "project_endpoint", "https://example.test/project")
    monkeypatch.setattr(settings, "agent_name", "buildingassist-agent")

    answer, citations = client.ask("What is happening at Paris HQ?")

    assert answer == "Simulated current data."
    assert citations == []
    assert responses.kwargs == {
        "input": "What is happening at Paris HQ?",
        "extra_body": {
            "agent_reference": {
                "name": "buildingassist-agent",
                "id": "agent-resource-id",
                "type": "agent_reference",
            }
        },
    }


def test_foundry_request_combines_foundry_iq_with_read_only_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = _FakeResponses()
    client = FoundryAgentClient()
    client._openai_client = SimpleNamespace(responses=responses)
    client._search_token_provider = lambda: "search-token"

    monkeypatch.setattr(settings, "use_mock_agent", False)
    monkeypatch.setattr(settings, "project_endpoint", "https://example.test/project")
    monkeypatch.setattr(settings, "agent_name", "")
    monkeypatch.setattr(
        settings,
        "knowledge_mcp_endpoint",
        "https://search.example.test/knowledgebases/buildingassist/mcp",
    )
    monkeypatch.setattr(settings, "mcp_server_url", "https://api.example.test/mcp/")

    answer, citations = client.ask("What is happening at Paris HQ?")

    assert answer == "Simulated current data."
    assert citations == []
    assert responses.kwargs["model"] == settings.model_deployment
    knowledge_tool, operations_tool = responses.kwargs["tools"]
    assert knowledge_tool["allowed_tools"] == ["knowledge_base_retrieve"]
    assert knowledge_tool["headers"] == {"Authorization": "Bearer search-token"}
    assert operations_tool["server_url"] == "https://api.example.test/mcp/"
    assert operations_tool["allowed_tools"] == READ_ONLY_TOOLS
    assert operations_tool["require_approval"] == "never"