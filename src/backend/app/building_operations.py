"""Deterministic, in-memory smart-building operations simulator."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Literal

_DEFAULT_DATA_PATH = Path(__file__).parent / "data" / "building_operations.json"


class BuildingOperations:
    """Serve fictional telemetry and apply reversible simulated operations."""

    def __init__(self, data_path: Path = _DEFAULT_DATA_PATH) -> None:
        self._data_path = data_path
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock, self._data_path.open(encoding="utf-8") as data_file:
            self._state = json.load(data_file)

    def list_buildings(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": building["id"],
                    "name": building["name"],
                    "city": building["city"],
                }
                for building in self._state["buildings"]
            ]

    def get_building_information(self, building_id: str) -> dict:
        with self._lock:
            building = self._building(building_id)
            return {
                "id": building["id"],
                "name": building["name"],
                "city": building["city"],
                "timezone": building["timezone"],
                **deepcopy(building["information"]),
                "zones": [
                    {"id": zone["id"], "name": zone["name"]}
                    for zone in building["zones"]
                ],
                "action_policy": deepcopy(building["action_policy"]),
            }

    def get_building_data(self, building_id: str) -> dict:
        with self._lock:
            building = self._building(building_id)
            return {
                "building_id": building["id"],
                "as_of": self._state["as_of"],
                "operating_status": building["operating_status"],
                "telemetry": deepcopy(building["telemetry"]),
                "zones": deepcopy(building["zones"]),
                "active_alerts": [
                    deepcopy(alert) for alert in building["alerts"] if alert["active"]
                ],
            }

    def create_work_order(
        self,
        building_id: str,
        title: str,
        reason: str,
        priority: Literal["low", "medium", "high"] = "medium",
    ) -> dict:
        if not title.strip() or not reason.strip():
            raise ValueError("A work order requires a title and reason.")
        if priority not in {"low", "medium", "high"}:
            raise ValueError("Priority must be low, medium, or high.")

        with self._lock:
            building = self._building(building_id)
            work_order = {
                "id": f"WO-{len(self._state['work_orders']) + 1:04d}",
                "building_id": building["id"],
                "building_name": building["name"],
                "title": title.strip(),
                "reason": reason.strip(),
                "priority": priority,
                "status": "created",
                "simulation": True,
                "created_at": self._now(),
            }
            self._state["work_orders"].append(work_order)
            return deepcopy(work_order)

    def set_hvac_setpoint(
        self,
        building_id: str,
        zone_id: str,
        temperature_c: float,
        duration_minutes: int,
        reason: str,
        confirmed: bool = False,
    ) -> dict:
        if not confirmed:
            return {
                "status": "confirmation_required",
                "simulation": True,
                "message": "No change applied. Ask the user to confirm the HVAC adjustment.",
            }
        if not reason.strip():
            raise ValueError("A reason is required for an HVAC adjustment.")

        with self._lock:
            building = self._building(building_id)
            zone = self._zone(building, zone_id)
            policy = building["action_policy"]
            if zone["id"] in policy["blocked_hvac_zone_ids"]:
                raise ValueError(
                    f"Zone {zone['id']!r} is not eligible for HVAC adjustments."
                )
            minimum = policy["minimum_setpoint_c"]
            maximum = policy["maximum_setpoint_c"]
            max_duration = policy["maximum_duration_minutes"]
            if not minimum <= temperature_c <= maximum:
                raise ValueError(
                    f"Setpoint must be between {minimum:.1f} C and {maximum:.1f} C."
                )
            if not 1 <= duration_minutes <= max_duration:
                raise ValueError(
                    f"Duration must be between 1 and {max_duration} minutes."
                )

            previous_setpoint = zone["setpoint_c"]
            zone["setpoint_c"] = temperature_c
            building["telemetry"]["hvac_setpoint_c"] = temperature_c
            action = {
                "id": f"ACT-{len(self._state['actions']) + 1:04d}",
                "type": "temporary_hvac_setpoint",
                "building_id": building["id"],
                "zone_id": zone["id"],
                "previous_setpoint_c": previous_setpoint,
                "setpoint_c": temperature_c,
                "duration_minutes": duration_minutes,
                "reason": reason.strip(),
                "status": "applied",
                "simulation": True,
                "applied_at": self._now(),
                "expires_at": self._future_time(duration_minutes),
            }
            self._state["actions"].append(action)
            return deepcopy(action)

    def _building(self, building_id: str) -> dict:
        normalized = building_id.strip().lower()
        for building in self._state["buildings"]:
            if building["id"] == normalized:
                return building
        raise ValueError(f"Unknown building_id {building_id!r}.")

    @staticmethod
    def _zone(building: dict, zone_id: str) -> dict:
        normalized = zone_id.strip().lower()
        for zone in building["zones"]:
            if zone["id"] == normalized:
                return zone
        raise ValueError(
            f"Unknown zone_id {zone_id!r} for building {building['id']!r}."
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _future_time(duration_minutes: int) -> str:
        return (
            datetime.now(UTC) + timedelta(minutes=duration_minutes)
        ).isoformat().replace("+00:00", "Z")


operations = BuildingOperations()