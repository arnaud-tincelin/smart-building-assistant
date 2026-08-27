"""API tests for the BuildingAssist backend.

The Foundry client is mocked so tests run without Azure credentials or network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Citation


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient with the Foundry agent call stubbed out."""

    def fake_ask(self, question: str):  # noqa: ANN001, ARG001
        return (
            f"Mocked answer for: {question}",
            [Citation(title="Sample doc", url="https://example.com/doc", snippet="…")],
        )

    monkeypatch.setattr("app.foundry_client.FoundryAgentClient.ask", fake_ask)
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


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


def test_ask_surfaces_foundry_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self, question: str):  # noqa: ANN001, ARG001
        raise RuntimeError("Foundry is not configured.")

    monkeypatch.setattr("app.foundry_client.FoundryAgentClient.ask", boom)
    resp = TestClient(app).post("/ask", json={"question": "hi"})
    assert resp.status_code == 502
    assert "Foundry is not configured." in resp.json()["detail"]


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
