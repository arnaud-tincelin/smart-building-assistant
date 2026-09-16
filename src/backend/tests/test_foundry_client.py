from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import foundry_client
from app.agent_policy import READ_ONLY_MCP_TOOLS
from app.config import settings
from app.foundry_client import FoundryAgentClient


class _FakeResponses:
    def __init__(self) -> None:
        self.kwargs: dict = {}
        self.result = SimpleNamespace(output_text="Simulated current data.", output=[])

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.kwargs = kwargs
        return self.result


@pytest.fixture(autouse=True)
def router_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(foundry_client, "known_mode", lambda: "balanced")


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
    monkeypatch.setattr(settings, "project_endpoint",
                        "https://example.test/project")
    monkeypatch.setattr(settings, "agent_name", "buildingassist-agent")

    result = client.ask("What is happening at Paris HQ?")

    assert result.answer == "Simulated current data."
    assert result.citations == []
    assert result.execution.mode == "agents"
    assert result.execution.selected_model is None
    assert result.execution.usage is None
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
    monkeypatch.setattr(settings, "project_endpoint",
                        "https://example.test/project")
    monkeypatch.setattr(settings, "agent_name", "")
    monkeypatch.setattr(
        settings,
        "knowledge_mcp_endpoint",
        "https://search.example.test/knowledgebases/buildingassist/mcp",
    )
    monkeypatch.setattr(settings, "mcp_server_url",
                        "https://api.example.test/mcp/")
    monkeypatch.setattr(settings, "gateway_api_key", "gateway-key")

    result = client.ask("What is happening at Paris HQ?")

    assert result.answer == "Simulated current data."
    assert result.citations == []
    assert responses.kwargs["model"] == settings.model_deployment
    knowledge_tool, operations_tool = responses.kwargs["tools"]
    assert knowledge_tool["allowed_tools"] == ["knowledge_base_retrieve"]
    assert knowledge_tool["headers"] == {
        "Authorization": "Bearer search-token"}
    assert operations_tool["server_url"] == "https://api.example.test/mcp/"
    assert operations_tool["allowed_tools"] == READ_ONLY_MCP_TOOLS
    assert operations_tool["require_approval"] == "never"
    assert operations_tool["headers"] == {"Api-Key": "gateway-key"}


def test_foundry_returns_real_execution_measurements(monkeypatch) -> None:
    responses = _FakeResponses()
    responses.result = SimpleNamespace(
        output_text="Current building data.",
        model="gpt-4o-mini-2024-07-18",
        id="resp-test",
        status="completed",
        usage=SimpleNamespace(
            input_tokens=100, output_tokens=30, total_tokens=130,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=10),
        ),
        output=[
            SimpleNamespace(type="mcp_list_tools", name="not-a-call"),
            SimpleNamespace(type="mcp_call", name="operations_getBuildingData"),
            SimpleNamespace(type="mcp_call", name="operations_getBuildingData"),
        ],
    )
    clock = iter([10.0, 19.65])
    monkeypatch.setattr(foundry_client, "perf_counter", lambda: next(clock))
    result = FoundryAgentClient()._create_response(
        SimpleNamespace(responses=responses), {"input": "Hi"}
    )
    execution = result.execution
    assert execution.selected_model == "gpt-4o-mini-2024-07-18"
    assert execution.requested_model == settings.model_deployment
    assert execution.reported_model == execution.selected_model
    assert execution.routing_mode == "balanced"
    assert execution.latency_ms == 9650
    assert execution.response_id == "resp-test"
    assert execution.usage.total_tokens == 130
    assert execution.usage.cached_tokens == 0
    assert execution.usage.cache_write_tokens is None
    assert execution.tools_used == ["operations_getBuildingData"]


@pytest.mark.parametrize("status", ["failed", "incomplete", "cancelled"])
def test_failed_or_incomplete_agent_response_is_an_error(status) -> None:
    responses = _FakeResponses()
    responses.result.status = status
    with pytest.raises(RuntimeError, match=status):
        FoundryAgentClient()._create_response(SimpleNamespace(responses=responses), {})


def test_empty_agent_response_is_not_a_success() -> None:
    responses = _FakeResponses()
    responses.result.output_text = ""
    with pytest.raises(RuntimeError, match="did not return an answer"):
        FoundryAgentClient()._create_response(SimpleNamespace(responses=responses), {})
