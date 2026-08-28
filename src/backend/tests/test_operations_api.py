from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent_policy import ACTION_API_OPERATIONS, READ_ONLY_API_OPERATIONS
from app.main import app


def _operations_by_id(schema: dict) -> dict[str, tuple[str, str]]:
    return {
        operation["operationId"]: (method, path)
        for path, path_item in schema["paths"].items()
        if path.startswith("/operations/")
        for method, operation in path_item.items()
    }


def test_openapi_exposes_stable_operations_for_apim_tools() -> None:
    runtime_schema = TestClient(app).get("/openapi.json").json()
    deployed_schema_path = (
        Path(__file__).parents[3] / "infra/api/building-operations.openapi.json"
    )
    deployed_schema = json.loads(deployed_schema_path.read_text())
    expected_operation_ids = set(READ_ONLY_API_OPERATIONS + ACTION_API_OPERATIONS)

    assert set(_operations_by_id(runtime_schema)) == expected_operation_ids
    assert _operations_by_id(deployed_schema) == _operations_by_id(runtime_schema)


def test_operations_api_exposes_read_and_action_endpoints() -> None:
    client = TestClient(app)

    buildings = client.get("/operations/buildings")
    information = client.get("/operations/buildings/paris-hq/information")
    data = client.get("/operations/buildings/paris-hq/data")
    work_order = client.post(
        "/operations/work-orders",
        json={
            "building_id": "paris-hq",
            "title": "Inspect Floor 3 air handling unit",
            "reason": "Cooling demand is above baseline.",
            "priority": "high",
        },
    )
    setpoint = client.post(
        "/operations/hvac-setpoints",
        json={
            "building_id": "paris-hq",
            "zone_id": "floor-3",
            "temperature_c": 24.0,
            "duration_minutes": 60,
            "reason": "Reduce peak demand.",
        },
    )

    assert buildings.status_code == 200
    assert buildings.json()["simulation"] is True
    assert information.status_code == 200
    assert information.json()["building"]["id"] == "paris-hq"
    assert data.status_code == 200
    assert data.json()["data"]["telemetry"]["current_power_kw"] == 184.6
    assert work_order.status_code == 200
    assert work_order.json()["status"] == "created"
    assert setpoint.status_code == 200
    assert setpoint.json()["status"] == "confirmation_required"


def test_operations_api_rejects_unknown_building() -> None:
    response = TestClient(app).get("/operations/buildings/not-a-building/data")

    assert response.status_code == 400
    assert "Unknown building_id" in response.json()["detail"]