"""Tests for the Model Router routing-mode control endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import model_router
from app.config import settings
from app.main import app

DEPLOYMENT = {
    "sku": {"name": "GlobalStandard", "capacity": 30},
    "properties": {
        "model": {"format": "OpenAI", "name": "model-router", "version": "2025-11-18"},
        "routing": None,
    },
}


class FakeAdmin(model_router.ModelRouterAdmin):
    """Admin client with the ARM round trip replaced by an in-memory deployment."""

    def __init__(self) -> None:
        super().__init__("/subscriptions/s/deployments/model-router")
        self.state = {k: dict(v) if isinstance(v, dict) else v for k, v in DEPLOYMENT.items()}
        self.puts: list[dict] = []

    def _request(self, method: str, body=None):  # noqa: ANN001, ANN202
        if method == "PUT":
            self.puts.append(body)
            self.state["properties"]["routing"] = body["properties"]["routing"]
            return body
        return self.state


@pytest.fixture()
def admin(monkeypatch: pytest.MonkeyPatch) -> FakeAdmin:
    fake = FakeAdmin()
    monkeypatch.setattr(settings, "enable_router_control", True)
    monkeypatch.setattr(model_router, "get_admin", lambda: fake)
    monkeypatch.setattr("app.main.get_admin", lambda: fake)
    return fake


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_unset_routing_reports_balanced(admin: FakeAdmin, client: TestClient) -> None:
    body = client.get("/model-router/mode").json()
    assert body["mode"] == "balanced"
    assert body["explicitly_set"] is False
    assert body["editable"] is True


def test_set_mode_writes_minimal_body(admin: FakeAdmin, client: TestClient) -> None:
    resp = client.put("/model-router/mode", json={"mode": "quality"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "quality"
    assert resp.json()["explicitly_set"] is True

    (put,) = admin.puts
    assert put["properties"]["routing"] == {"mode": "quality"}
    assert put["properties"]["model"]["version"] == "2025-11-18"
    assert put["sku"] == {"name": "GlobalStandard", "capacity": 30}
    # Read-only server state must not be echoed back to ARM.
    assert "provisioningState" not in put["properties"]


def test_set_mode_preserves_model_subset(admin: FakeAdmin, client: TestClient) -> None:
    subset = [{"format": "OpenAI", "name": "gpt-4.1", "version": "2025-04-14"}]
    admin.state["properties"]["routing"] = {"mode": "balanced", "models": subset}

    client.put("/model-router/mode", json={"mode": "cost"})

    (put,) = admin.puts
    assert put["properties"]["routing"] == {"mode": "cost", "models": subset}


def test_rejects_unknown_mode(admin: FakeAdmin, client: TestClient) -> None:
    assert client.put("/model-router/mode", json={"mode": "cheapest"}).status_code == 422


def test_disabled_control_is_read_only(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(settings, "enable_router_control", False)

    body = client.get("/model-router/mode").json()
    assert body["editable"] is False
    assert client.put("/model-router/mode", json={"mode": "cost"}).status_code == 403


def test_known_mode_tracks_last_read(admin: FakeAdmin, client: TestClient) -> None:
    client.put("/model-router/mode", json={"mode": "quality"})
    assert model_router.known_mode() == "quality"
