from __future__ import annotations

import pytest

from app.building_operations import BuildingOperations


@pytest.fixture()
def operations() -> BuildingOperations:
    return BuildingOperations()


def test_lists_buildings_and_separates_information_from_current_data(
    operations: BuildingOperations,
) -> None:
    buildings = operations.list_buildings()
    information = operations.get_building_information("paris-hq")
    data = operations.get_building_data("paris-hq")

    assert [building["id"] for building in buildings] == [
        "paris-hq",
        "seattle-lab",
        "munich-ops",
    ]
    assert information["gross_floor_area_m2"] == 18400
    assert "highest afternoon cooling sensitivity" in information["specificities"][1]
    assert "telemetry" not in information
    assert data["telemetry"]["current_power_kw"] == 184.6
    assert data["zones"][0]["co2_ppm"] == 1180
    assert data["zones"][0]["relative_humidity_percent"] == 58
    assert data["as_of"] == "2026-08-27T09:00:00Z"
    assert data["active_alerts"][0]["id"] == "ALT-PAR-001"
    assert "specificities" not in data


def test_creates_a_simulated_work_order(operations: BuildingOperations) -> None:
    work_order = operations.create_work_order(
        "paris-hq",
        "Inspect Floor 3 air handling unit",
        "Cooling demand is above baseline.",
        "high",
    )

    assert work_order["id"] == "WO-0001"
    assert work_order["simulation"] is True
    assert work_order["status"] == "created"


def test_hvac_change_requires_confirmation_and_enforces_policy(
    operations: BuildingOperations,
) -> None:
    pending = operations.set_hvac_setpoint(
        "paris-hq", "floor-3", 24.0, 60, "Reduce peak demand."
    )
    assert pending["status"] == "confirmation_required"
    assert operations.get_building_data("paris-hq")["zones"][0]["setpoint_c"] == 23.0

    with pytest.raises(ValueError, match="between 20.0 C and 26.0 C"):
        operations.set_hvac_setpoint(
            "paris-hq", "floor-3", 28.0, 60, "Reduce peak demand.", True
        )

    applied = operations.set_hvac_setpoint(
        "paris-hq", "floor-3", 24.0, 60, "Reduce peak demand.", True
    )
    assert applied["status"] == "applied"
    assert applied["previous_setpoint_c"] == 23.0
    assert operations.get_building_data("paris-hq")["zones"][0]["setpoint_c"] == 24.0


def test_unknown_building_is_rejected(operations: BuildingOperations) -> None:
    with pytest.raises(ValueError, match="Unknown building_id"):
        operations.get_building_data("not-a-building")


def test_comfort_critical_zone_rejects_hvac_action(
    operations: BuildingOperations,
) -> None:
    with pytest.raises(ValueError, match="not eligible"):
        operations.set_hvac_setpoint(
            "munich-ops",
            "dispatch",
            23.0,
            30,
            "Reduce demand.",
            True,
        )