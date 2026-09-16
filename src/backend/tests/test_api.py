"""API tests for the BuildingAssist backend.

The Foundry client is mocked so tests run without Azure credentials or network.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import RateLimitError

from app.config import settings
from app.foundry_client import FoundryAgentClient
from app.main import app
from app.models import AskResponse, Citation


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient with the Foundry agent call stubbed out."""

    def fake_ask(self, question: str):  # noqa: ANN001, ARG001
        return AskResponse(
            answer=f"Mocked answer for: {question}",
            citations=[Citation(title="Sample doc", url="https://example.com/doc", snippet="…")],
        )

    monkeypatch.setattr("app.foundry_client.FoundryAgentClient.ask", fake_ask)
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_invalid_operations_source_returns_diagnosable_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("app.main.settings.operations_source", "digital-twins-prod")
    caplog.set_level("ERROR", logger="buildingassist.api")

    response = client.get("/healthz", headers={"Origin": "https://frontend.example"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "invalid_runtime_configuration"
    assert response.headers["access-control-allow-origin"] == "*"
    assert any("CONFIG_ERROR" in record.message for record in caplog.records)


def test_ask_returns_answer_and_citations(client: TestClient) -> None:
    resp = client.post("/ask", json={"question": "How much energy did Floor 3 use this week?"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["answer"].startswith("Mocked answer for:")
    assert len(body["citations"]) == 1
    assert body["citations"][0]["title"] == "Sample doc"


def test_ask_rejects_empty_question(client: TestClient) -> None:
    resp = client.post("/ask", json={"question": ""})
    assert resp.status_code == 422


def test_ask_rejects_unknown_mode(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "Hi", "mode": "compliance"})
    assert response.status_code == 422


def test_agents_mode_does_not_call_gateway(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.get_gateway_client", lambda: pytest.fail("Unexpected gateway call")
    )
    response = client.post("/ask", json={"question": "Hi", "mode": "agents"})
    assert response.status_code == 200
    assert response.json()["answer"] == "Mocked answer for: Hi"


def test_gateway_mode_never_falls_back_to_agent(client: TestClient, monkeypatch) -> None:
    from app.gateway_client import GatewayError

    def unavailable():
        raise GatewayError("Gateway is unavailable.", status=503)

    monkeypatch.setattr("app.main.get_gateway_client", unavailable)
    response = client.post("/ask", json={"question": "Hi", "mode": "gateway"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Gateway is unavailable."


def test_router_put_is_allowed_by_cors(client: TestClient) -> None:
    response = client.options("/model-router/mode", headers={
        "Origin": "https://frontend.example",
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_ask_surfaces_foundry_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self, question: str):  # noqa: ANN001, ARG001
        raise RuntimeError("Foundry is not configured.")

    monkeypatch.setattr("app.foundry_client.FoundryAgentClient.ask", boom)
    resp = TestClient(app).post("/ask", json={"question": "hi"})
    assert resp.status_code == 502
    assert "Foundry is not configured." in resp.json()["detail"]


def test_foundry_rate_limit_keeps_status_retry_hint_and_cors(monkeypatch) -> None:
    def limited(**kwargs):
        raise RateLimitError(
            "Rate limit exceeded",
            response=httpx.Response(
                429, headers={"Retry-After": "21"},
                request=httpx.Request("POST", "https://example.test/responses"),
            ),
            body=None,
        )

    foundry = FoundryAgentClient()
    foundry._openai_client = SimpleNamespace(responses=SimpleNamespace(create=limited))
    monkeypatch.setattr(settings, "use_mock_agent", False)
    monkeypatch.setattr(settings, "project_endpoint", "https://example.test/project")
    monkeypatch.setattr(settings, "agent_name", "")
    monkeypatch.setattr(settings, "knowledge_mcp_endpoint", "")
    monkeypatch.setattr(settings, "mcp_server_url", "")
    monkeypatch.setattr("app.foundry_client.known_mode", lambda: "balanced")
    monkeypatch.setattr("app.main.get_client", lambda: foundry)

    response = TestClient(app).post(
        "/ask", json={"question": "Hi", "mode": "agents"},
        headers={"Origin": "https://frontend.example"},
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "21"
    assert response.headers["access-control-allow-origin"] == "*"
    assert "rate-limited" in response.json()["detail"]
    assert "Retry after 21s" in response.json()["detail"]


@pytest.mark.parametrize(
    ("path", "payload", "operation"),
    [
        (
            "/security/access-requests",
            {
                "building_id": "paris-hq",
                "access_point_id": "main-lobby",
                "credential_id": "BDG-1042",
                "method": "badge",
            },
            "access_request",
        ),
        (
            "/security/visitors/check-in",
            {
                "building_id": "paris-hq",
                "access_point_id": "main-lobby",
                "visitor_name": "Jordan Lee",
                "visitor_email": "jordan.lee@example.com",
                "host_name": "Morgan Chen",
                "purpose": "Energy audit",
            },
            "visitor_check_in",
        ),
    ],
)
def test_security_demo_operations_surface_diagnosable_server_error(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    path: str,
    payload: dict[str, str],
    operation: str,
) -> None:
    caplog.set_level("ERROR", logger="buildingassist.security")

    response = client.post(path, json=payload)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "security_control_failure"
    assert detail["operation"] == operation
    assert detail["incident_id"].startswith("SEC-")
    assert response.headers["x-incident-id"] == detail["incident_id"]
    assert any(
        record.operation == operation and record.incident_id == detail["incident_id"]
        for record in caplog.records
    )
