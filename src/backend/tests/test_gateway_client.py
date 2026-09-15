"""Tests for the governed lane that routes model calls through the AI Gateway."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.error import HTTPError

import httpx
import pytest
from fastapi.testclient import TestClient

from app import gateway_client
from app.gateway_client import GatewayError, GatewayModelClient
from app.main import app

COMPLETION = {
    "id": "chatcmpl-test",
    "model": "gpt-5-mini-2025-08-07",
    "choices": [{"message": {"role": "assistant", "content": "Cooling load peaks midafternoon."}}],
    "usage": {"prompt_tokens": 40, "completion_tokens": 12, "total_tokens": 52},
}


class FakeResponse:
    def __init__(self, payload: dict, headers: dict[str, str]) -> None:
        self._payload = json.dumps(payload).encode()
        self.headers = headers

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_) -> None:
        return None


@pytest.fixture()
def gateway(monkeypatch: pytest.MonkeyPatch) -> GatewayModelClient:
    client = GatewayModelClient("https://gw.example/openai/v1", "key", "gpt-5-mini")
    monkeypatch.setattr("app.main.get_gateway_client", lambda: client)
    return client


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def no_router_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.model_router.get_admin", lambda: pytest.fail("Gateway must not query Model Router")
    )


def _http_error(status: int, headers: dict[str, str] | None = None) -> HTTPError:
    import io

    return HTTPError(
        "https://gw.example", status, "err", headers or {}, io.BytesIO(b"{}")
    )


def test_gateway_mode_reports_gateway_execution(
    gateway: GatewayModelClient, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = {"x-ratelimit-remaining-tokens": "29983", "x-ratelimit-limit-tokens": "30000"}
    monkeypatch.setattr(
        gateway_client, "urlopen", lambda *a, **k: FakeResponse(COMPLETION, headers)
    )

    body = client.post("/ask", json={"question": "Why?", "mode": "gateway"}).json()

    assert body["answer"] == "Cooling load peaks midafternoon."
    assert body["citations"] == []
    assert body["execution"]["mode"] == "gateway"
    assert body["execution"]["routing_mode"] is None
    assert body["execution"]["selected_model"] == "gpt-5-mini-2025-08-07"
    assert body["execution"]["requested_model"] == "gpt-5-mini"
    assert "Model Router is not used" in body["execution"]["routing_explanation"]
    assert body["execution"]["usage"]["total_tokens"] == 52
    assert "29983 of 30000" in body["execution"]["routing_explanation"]


def test_content_safety_block_is_surfaced(
    gateway: GatewayModelClient, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The gateway answers 403 on a content safety block, not the documented 400.
    def raise_403(*_a, **_k):
        raise _http_error(403)

    monkeypatch.setattr(gateway_client, "urlopen", raise_403)

    resp = client.post("/ask", json={"question": "bad", "mode": "gateway"})
    # A policy block must not surface as 5xx, or it would trip the backend SRE alert.
    assert resp.status_code == 403
    assert "content safety" in resp.json()["detail"]


def test_rate_limit_includes_retry_hint(
    gateway: GatewayModelClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_429(*_a, **_k):
        raise _http_error(429, {"Retry-After": "37"})

    monkeypatch.setattr(gateway_client, "urlopen", raise_429)

    with pytest.raises(GatewayError, match="Retry after 37s"):
        gateway.ask("anything")


def test_unconfigured_gateway_reports_missing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "gateway_model_endpoint", "")
    gateway_client.get_gateway_client.cache_clear()

    with pytest.raises(GatewayError, match="GATEWAY_MODEL_ENDPOINT"):
        gateway_client.get_gateway_client()

    gateway_client.get_gateway_client.cache_clear()


def test_gateway_executes_read_only_mcp_tool_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_name = "operations_listBuildings"
    tool_calls = []
    requests = []

    class ToolSession:
        async def list_tools(self, params=None):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name=name, description="Building operation", inputSchema={"type": "object"}
                    )
                    for name in [tool_name, "operations_setHvacSetpoint"]
                ],
                nextCursor=None,
            )

        async def call_tool(self, name, arguments):
            tool_calls.append((name, arguments))
            return SimpleNamespace(
                isError=False,
                model_dump=lambda **kwargs: {
                    "content": [{"type": "text", "text": "Contoso Tower"}], "isError": False
                },
            )

    @asynccontextmanager
    async def open_session(endpoint, api_key):
        assert endpoint == "https://gw.example/default/toolservers/building-operations/mcp"
        assert api_key == "key"
        yield ToolSession()

    def complete(request, **kwargs):
        body = json.loads(request.data)
        requests.append(body)
        if len(requests) == 1:
            return FakeResponse({
                **COMPLETION,
                "choices": [{"message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": "call-buildings", "type": "function", "function": {
                        "name": tool_name, "arguments": "{}"
                    }}],
                }}],
            }, {})
        return FakeResponse(COMPLETION, {})

    monkeypatch.setattr(gateway_client, "open_tool_session", open_session, raising=False)
    monkeypatch.setattr(gateway_client, "urlopen", complete)
    gateway = GatewayModelClient(
        "https://gw.example/openai/v1", "key", "gpt-5-mini",
        mcp_server_url="https://gw.example/default/toolservers/building-operations/mcp",
    )

    result = gateway.ask("List the buildings")

    assert tool_calls == [(tool_name, {})]
    assert len(requests) == 2
    assert all(request["model"] == "gpt-5-mini" for request in requests)
    assert [tool["function"]["name"] for tool in requests[0]["tools"]] == [tool_name]
    assert requests[1]["messages"][-1]["role"] == "tool"
    assert requests[1]["messages"][-1]["tool_call_id"] == "call-buildings"
    assert "Contoso Tower" in requests[1]["messages"][-1]["content"]
    assert result.execution.tools_used == [tool_name]
    assert result.execution.usage.total_tokens == 104
    assert result.execution.mode == "gateway"
    assert result.execution.routing_mode is None


def tool_completion(*names: str, arguments: str = "{}") -> dict:
    return {
        **COMPLETION,
        "choices": [{"message": {
            "role": "assistant", "content": None,
            "tool_calls": [
                {"id": f"call-{index}", "type": "function", "function": {
                    "name": name, "arguments": arguments,
                }}
                for index, name in enumerate(names)
            ],
        }}],
    }


@pytest.fixture()
def mcp_gateway(monkeypatch: pytest.MonkeyPatch):
    state = {
        "methods": [], "calls": [], "status": None, "tool_error": False,
        "pages": [["operations_listBuildings", "operations_getBuildingData",
                   "operations_setHvacSetpoint"]],
    }

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://gw.example/default/toolservers/building-operations/mcp"
        assert request.headers["Api-Key"] == "key"
        body = json.loads(request.content)
        method = body["method"]
        state["methods"].append(method)
        if state["status"]:
            return httpx.Response(state["status"], headers={"Retry-After": "7"})
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                "serverInfo": {"name": "gateway-test", "version": "1.0"},
            }
        elif method == "tools/list":
            page_index = int(body.get("params", {}).get("cursor", "0"))
            result = {"tools": [
                {"name": name, "description": "Building operation",
                 "inputSchema": {"type": "object"}}
                for name in state["pages"][page_index]
            ]}
            if page_index + 1 < len(state["pages"]):
                result["nextCursor"] = str(page_index + 1)
        elif method == "tools/call":
            state["calls"].append(body["params"])
            result = {
                "content": [{"type": "text", "text": "Contoso Tower"}],
                "structuredContent": {"building": "Contoso Tower"},
                "isError": state["tool_error"],
            }
        else:
            pytest.fail(f"Unexpected MCP method: {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        gateway_client.httpx, "AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    return GatewayModelClient(
        "https://gw.example/openai/v1", "key", "gpt-5-mini",
        mcp_server_url="https://gw.example/default/toolservers/building-operations/mcp",
    ), state


def test_mcp_sdk_discovers_pages_and_handles_multiple_calls(mcp_gateway, monkeypatch):
    gateway, state = mcp_gateway
    state["pages"] = [
        ["operations_listBuildings", "operations_setHvacSetpoint"],
        ["operations_getBuildingData"],
    ]
    requests = []

    def complete(request, **kwargs):
        requests.append(json.loads(request.data))
        if len(requests) == 1:
            return FakeResponse(tool_completion(
                "operations_listBuildings", "operations_getBuildingData"
            ), {})
        return FakeResponse(COMPLETION, {})

    monkeypatch.setattr(gateway_client, "urlopen", complete)
    result = gateway.ask("List buildings and their readings")

    assert "initialize" in state["methods"]
    assert "notifications/initialized" in state["methods"]
    assert state["methods"].count("tools/list") == 2
    assert [call["name"] for call in state["calls"]] == [
        "operations_listBuildings", "operations_getBuildingData"
    ]
    assert [tool["function"]["name"] for tool in requests[0]["tools"]] == [
        "operations_listBuildings", "operations_getBuildingData"
    ]
    assert [message["tool_call_id"] for message in requests[1]["messages"][-2:]] == [
        "call-0", "call-1"
    ]
    assert "structuredContent" in requests[1]["messages"][-1]["content"]
    assert result.execution.tools_used == ["operations_listBuildings", "operations_getBuildingData"]
    assert result.execution.usage.total_tokens == 104


@pytest.mark.parametrize("name,arguments,reason", [
    ("operations_setHvacSetpoint", "{}", "not allowed"),
    ("unknown_tool", "{}", "not allowed"),
    ("operations_listBuildings", "not-json", "invalid tool arguments"),
    ("operations_listBuildings", "[]", "invalid tool arguments"),
    ("operations_listBuildings", "null", "invalid tool arguments"),
])
def test_invalid_tool_calls_never_execute(mcp_gateway, monkeypatch, name, arguments, reason):
    gateway, state = mcp_gateway
    monkeypatch.setattr(gateway_client, "urlopen", lambda *args, **kwargs: FakeResponse(
        tool_completion(name, arguments=arguments), {}
    ))

    with pytest.raises(GatewayError, match=reason):
        gateway.ask("Change the building")
    assert state["calls"] == []


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_mcp_transport_failures_are_controlled(mcp_gateway, monkeypatch, status):
    gateway, state = mcp_gateway
    state["status"] = status
    monkeypatch.setattr("app.main.get_gateway_client", lambda: gateway)
    response = TestClient(app).post("/ask", json={"question": "List", "mode": "gateway"})
    assert response.status_code == (status if status in (401, 403, 429) else 502)
    if status == 429:
        assert "Retry after 7s" in response.json()["detail"]
    assert state["calls"] == []


def test_mcp_tool_error_stops_without_fabricating_an_answer(mcp_gateway, monkeypatch):
    gateway, state = mcp_gateway
    state["tool_error"] = True
    monkeypatch.setattr(gateway_client, "urlopen", lambda *args, **kwargs: FakeResponse(
        tool_completion("operations_listBuildings"), {}
    ))
    with pytest.raises(GatewayError, match="operations_listBuildings failed"):
        gateway.ask("List the buildings")
    assert len(state["calls"]) == 1


def test_empty_read_only_catalog_fails_closed(mcp_gateway, monkeypatch):
    gateway, state = mcp_gateway
    state["pages"] = [["operations_setHvacSetpoint"]]
    monkeypatch.setattr(gateway_client, "urlopen", lambda *args, **kwargs: pytest.fail(
        "Model must not be called with a missing catalog"
    ))
    with pytest.raises(GatewayError, match="no approved building tools"):
        gateway.ask("List the buildings")


def test_tool_loop_is_bounded(mcp_gateway, monkeypatch):
    gateway, state = mcp_gateway
    requests = []

    def complete(request, **kwargs):
        requests.append(json.loads(request.data))
        return FakeResponse(tool_completion("operations_listBuildings"), {})

    monkeypatch.setattr(gateway_client, "urlopen", complete)
    with pytest.raises(GatewayError, match="tool-call limit"):
        gateway.ask("Keep checking")
    assert len(state["calls"]) == gateway_client.MAX_TOOL_ROUNDS
    assert len(requests) == gateway_client.MAX_TOOL_ROUNDS + 1
    assert requests[-1]["tool_choice"] == "none"


def test_tool_call_budget_blocks_oversized_batch(mcp_gateway, monkeypatch):
    gateway, state = mcp_gateway
    monkeypatch.setattr(gateway_client, "MAX_TOOL_CALLS", 1)
    monkeypatch.setattr(gateway_client, "urlopen", lambda *args, **kwargs: FakeResponse(
        tool_completion("operations_listBuildings", "operations_getBuildingData"), {}
    ))
    with pytest.raises(GatewayError, match="tool-call limit"):
        gateway.ask("List and check")
    assert state["calls"] == []


def test_general_answer_does_not_require_tool_execution(mcp_gateway, monkeypatch):
    gateway, state = mcp_gateway
    monkeypatch.setattr(gateway_client, "urlopen", lambda *args, **kwargs: FakeResponse(
        COMPLETION, {}
    ))
    result = gateway.ask("What generally drives cooling demand?")
    assert result.answer == COMPLETION["choices"][0]["message"]["content"]
    assert result.execution.tools_used == []
    assert result.execution.usage.total_tokens == 52
    assert state["calls"] == []


def test_configured_gateway_receives_existing_mcp_endpoint(monkeypatch):
    monkeypatch.setattr(gateway_client.settings, "gateway_model_endpoint", "https://gw.example/v1")
    monkeypatch.setattr(gateway_client.settings, "gateway_api_key", "key")
    monkeypatch.setattr(gateway_client.settings, "mcp_server_url", "https://gw.example/mcp")
    gateway_client.get_gateway_client.cache_clear()
    try:
        configured = gateway_client.get_gateway_client()
        assert configured._mcp_server_url == "https://gw.example/mcp"
        assert configured._model == "gpt-5-mini"
    finally:
        gateway_client.get_gateway_client.cache_clear()


def test_gateway_request_deadline_is_enforced(mcp_gateway, monkeypatch):
    gateway, _ = mcp_gateway

    async def stalled_tool(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(gateway_client, "REQUEST_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(gateway_client.ClientSession, "call_tool", stalled_tool)
    monkeypatch.setattr(gateway_client, "urlopen", lambda *args, **kwargs: FakeResponse(
        tool_completion("operations_listBuildings"), {}
    ))
    with pytest.raises(GatewayError, match="timed out") as caught:
        gateway.ask("List the buildings")
    assert caught.value.status == 504


def test_discovery_pagination_is_bounded(mcp_gateway, monkeypatch):
    gateway, state = mcp_gateway
    state["pages"] = [["operations_listBuildings"], ["operations_getBuildingData"]]
    monkeypatch.setattr(gateway_client, "MAX_DISCOVERY_PAGES", 1)
    with pytest.raises(GatewayError, match="discovery exceeded"):
        gateway.ask("List the buildings")
    assert state["methods"].count("tools/list") == 1
    assert state["calls"] == []


@pytest.mark.parametrize("status", [403, 429])
def test_model_policy_block_after_tool_execution_preserves_status(mcp_gateway, monkeypatch, status):
    gateway, state = mcp_gateway

    def complete(request, **kwargs):
        if not state["calls"]:
            return FakeResponse(tool_completion("operations_listBuildings"), {})
        raise _http_error(status)

    monkeypatch.setattr(gateway_client, "urlopen", complete)
    with pytest.raises(GatewayError) as caught:
        gateway.ask("List the buildings")
    assert caught.value.status == status
    assert len(state["calls"]) == 1


def test_missing_usage_and_model_are_not_invented(gateway, monkeypatch) -> None:
    payload = {key: value for key, value in COMPLETION.items() if key not in ("model", "usage")}
    monkeypatch.setattr(gateway_client, "urlopen", lambda *a, **k: FakeResponse(payload, {}))
    execution = gateway.ask("Why?").execution
    assert execution.selected_model is None
    assert execution.reported_model is None
    assert execution.usage is None
    assert execution.requested_model == "gpt-5-mini"


@pytest.mark.parametrize("payload", [
    {},
    {"choices": []},
    {**COMPLETION, "choices": [{"message": {"content": ""}}]},
    {**COMPLETION, "choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]},
    {**COMPLETION, "model": 42},
    {**COMPLETION, "usage": []},
    {**COMPLETION, "usage": {"prompt_tokens_details": ["invalid"]}},
])
def test_invalid_or_empty_response_is_an_error(gateway, monkeypatch, payload) -> None:
    monkeypatch.setattr(gateway_client, "urlopen", lambda *a, **k: FakeResponse(payload, {}))
    with pytest.raises(GatewayError):
        gateway.ask("Why?")


def test_missing_usage_on_one_model_call_leaves_total_unknown(mcp_gateway, monkeypatch) -> None:
    gateway, state = mcp_gateway

    def complete(*_args, **_kwargs):
        if not state["calls"]:
            payload = tool_completion("operations_listBuildings")
            payload.pop("usage")
            return FakeResponse(payload, {})
        return FakeResponse(COMPLETION, {})

    monkeypatch.setattr(gateway_client, "urlopen", complete)
    result = gateway.ask("List buildings")
    assert result.execution.usage is None
    assert result.execution.tools_used == ["operations_listBuildings"]
