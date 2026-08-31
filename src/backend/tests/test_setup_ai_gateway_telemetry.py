from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def telemetry_setup() -> ModuleType:
    script_path = Path(__file__).parents[3] / \
        "scripts" / "setup_ai_gateway_telemetry.py"
    spec = importlib.util.spec_from_file_location(
        "setup_ai_gateway_telemetry", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configure_exporter_replaces_legacy_credentials(
    monkeypatch: pytest.MonkeyPatch,
    telemetry_setup: ModuleType,
) -> None:
    calls: list[tuple[str, dict | None]] = []

    def arm_request(
        _token: str,
        method: str,
        _resource_id: str,
        _api_version: str,
        body: dict | None = None,
        **_kwargs: object,
    ) -> dict:
        calls.append((method, body))
        if method == "GET":
            return {
                "properties": {
                    "kind": "OpenTelemetry",
                    "openTelemetry": {
                        "credentials": {"managedIdentity": {}},
                        "managedIdentity": {},
                    },
                }
            }
        return {}

    monkeypatch.setattr(telemetry_setup, "_arm_request", arm_request)

    telemetry_setup._configure_exporter(
        "token",
        "/subscriptions/test/resourceGroups/test/providers/Microsoft.ApiManagement/service/test",
        "/subscriptions/test/resourceGroups/test/providers/microsoft.insights/components/test",
        {
            "OTLPMetricsEndpoint": "https://metrics.example.test",
            "OTLPLogsEndpoint": "https://logs.example.test",
            "OTLPTracesEndpoint": "https://traces.example.test",
        },
    )

    assert [method for method, _body in calls] == ["GET", "DELETE", "PUT"]
    open_telemetry = calls[-1][1]["properties"]["openTelemetry"]
    assert open_telemetry["credentials"] == {
        "managedIdentity": {"resource": "https://monitor.azure.com"}
    }
    assert "managedIdentity" not in open_telemetry
    assert "headers" not in open_telemetry
