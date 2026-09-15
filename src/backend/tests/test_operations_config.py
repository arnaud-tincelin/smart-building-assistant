from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app
from app.models import AskResponse


@pytest.mark.parametrize("source", ["bms-prod", "", "SIMULATOR"])
def test_invalid_source_starts_but_blocks_operations(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, source: str
) -> None:
    monkeypatch.setenv("BUILDINGASSIST_OPERATIONS_SOURCE", source)
    monkeypatch.setenv("CONTAINER_APP_REVISION", "test-bad-revision")
    configured = Settings(_env_file=None)
    monkeypatch.setattr(settings, "operations_source", configured.operations_source)
    client = TestClient(app)

    assert client.get("/healthz").status_code == 200
    for path in (
        "/operations/buildings",
        "/operations/buildings/paris-hq/information",
        "/operations/buildings/paris-hq/data",
    ):
        response = client.get(path)
        assert response.status_code == 503
        assert response.headers["x-operations-config"] == "v1"
        assert response.headers["x-error-code"] == "configuration_error"
        assert response.headers["x-incident-id"].startswith("CFG-")
        assert response.headers["x-incident-id"] in response.json()["detail"]
    response = client.post("/operations/work-orders", json={
        "building_id": "paris-hq", "title": "Do not create", "reason": "Unavailable",
    })
    assert response.status_code == 503
    assert "BUILDINGASSIST_OPERATIONS_SOURCE" in caplog.text
    assert "supported=simulator" in caplog.text
    assert "test-bad-revision" in caplog.text


@pytest.mark.parametrize("scenario", [None, "quick", "live", "compliance", "governed"])
def test_chat_fails_before_calling_models_and_recovers(
    monkeypatch: pytest.MonkeyPatch, scenario: str | None
) -> None:
    class FakeClient:
        calls = 0

        def ask(self, *_args: object) -> AskResponse:
            self.calls += 1
            return AskResponse(answer="Recovered", citations=[])

    model = FakeClient()
    monkeypatch.setattr("app.main.get_client", lambda: model)
    monkeypatch.setattr("app.main.get_gateway_client", lambda: model)
    monkeypatch.setattr(settings, "operations_source", "bms-prod")
    client = TestClient(app)
    payload = {"question": "List the buildings.", "scenario": scenario}

    assert client.post("/ask", json=payload).status_code == 503
    assert model.calls == 0

    monkeypatch.setattr(settings, "operations_source", "simulator")
    assert client.post("/ask", json=payload).status_code == 200
    recovered = client.get("/operations/buildings")
    assert recovered.status_code == 200
    assert recovered.headers["x-operations-config"] == "v1"
    assert model.calls == 1