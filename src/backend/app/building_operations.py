"""Deterministic, in-memory smart-building operations simulator."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Literal

_DEFAULT_DATA_PATH = Path(__file__).parent / "data" / \
    "building_operations.json"


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
                "id": self._next_id("WO", self._state["work_orders"]),
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

    def request_access(
        self,
        building_id: str,
        access_point_id: str,
        credential_id: str,
        method: Literal["badge", "mobile"],
    ) -> dict:
        with self._lock:
            building = self._building(building_id)
            access_point = self._access_point(building["id"], access_point_id)
            credential = self._credential(credential_id)
            if method not in access_point["methods"]:
                raise ValueError(
                    f"Access point {access_point['id']!r} does not accept {method}.")
            if credential["method"] != method:
                raise ValueError(
                    "The credential type does not match the access method.")
            if credential["status"] != "active":
                raise ValueError("The credential is not active.")
            if building["id"] not in credential["building_ids"]:
                raise ValueError(
                    "The credential is not authorized for this building.")

            event = {
                "id": self._next_id("SEC-EVT", self._state["security"]["audit_events"]),
                "operation": "access_request",
                "building_id": building["id"],
                "access_point_id": access_point["id"],
                "credential_id": credential["id"],
                "method": method,
                "decision": "granted",
                "occurred_at": self._now(),
            }
            event["outbound_payload"] = self._serialize_security_event(event)
            self._state["security"]["audit_events"].append(event)
            return deepcopy(event)

    def check_in_visitor(
        self,
        building_id: str,
        access_point_id: str,
        visitor_name: str,
        visitor_email: str,
        host_name: str,
        purpose: str,
    ) -> dict:
        values = (visitor_name, visitor_email, host_name, purpose)
        if any(not value.strip() for value in values):
            raise ValueError(
                "Visitor name, email, host, and purpose are required.")

        with self._lock:
            building = self._building(building_id)
            access_point = self._access_point(building["id"], access_point_id)
            visitor = {
                "id": self._next_id("VIS", self._state["security"]["visitors"]),
                "building_id": building["id"],
                "access_point_id": access_point["id"],
                "visitor_name": visitor_name.strip(),
                "visitor_email": visitor_email.strip(),
                "host_name": host_name.strip(),
                "purpose": purpose.strip(),
                "status": "checked_in",
                "checked_in_at": self._now(),
            }
            event = {
                "id": self._next_id("SEC-EVT", self._state["security"]["audit_events"]),
                "operation": "visitor_check_in",
                "building_id": building["id"],
                "access_point_id": access_point["id"],
                "visitor_id": visitor["id"],
                "decision": "granted",
                "occurred_at": visitor["checked_in_at"],
            }
            event["outbound_payload"] = self._serialize_security_event(event)
            self._state["security"]["visitors"].append(visitor)
            self._state["security"]["audit_events"].append(event)
            return deepcopy(visitor)

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
                "id": self._next_id("ACT", self._state["actions"]),
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

    @staticmethod
    def _find(items: Iterable[dict], match: Callable[[dict], bool], error: str) -> dict:
        for item in items:
            if match(item):
                return item
        raise ValueError(error)

    def _building(self, building_id: str) -> dict:
        normalized = building_id.strip().lower()
        return self._find(
            self._state["buildings"],
            lambda building: building["id"] == normalized,
            f"Unknown building_id {building_id!r}.",
        )

    def _access_point(self, building_id: str, access_point_id: str) -> dict:
        normalized = access_point_id.strip().lower()
        return self._find(
            self._state["security"]["access_points"],
            lambda point: point["building_id"] == building_id and point["id"] == normalized,
            f"Unknown access_point_id {access_point_id!r} for building {building_id!r}.",
        )

    def _credential(self, credential_id: str) -> dict:
        normalized = credential_id.strip().upper()
        return self._find(
            self._state["security"]["credentials"],
            lambda credential: credential["id"] == normalized,
            f"Unknown credential_id {credential_id!r}.",
        )

    def _zone(self, building: dict, zone_id: str) -> dict:
        normalized = zone_id.strip().lower()
        return self._find(
            building["zones"],
            lambda zone: zone["id"] == normalized,
            f"Unknown zone_id {zone_id!r} for building {building['id']!r}.",
        )

    @staticmethod
    def _serialize_security_event(event: dict) -> str:
        return json.dumps(
            {
                "eventId": event["id"],
                "eventType": event["operation"],
                "occurredAt": event["occurred_at"],
            }
        )

    @staticmethod
    def _next_id(prefix: str, collection: list) -> str:
        return f"{prefix}-{len(collection) + 1:04d}"

    @staticmethod
    def _iso_z(moment: datetime) -> str:
        return moment.isoformat().replace("+00:00", "Z")

    def _now(self) -> str:
        return self._iso_z(datetime.now(UTC))

    def _future_time(self, duration_minutes: int) -> str:
        return self._iso_z(datetime.now(UTC) + timedelta(minutes=duration_minutes))


operations = BuildingOperations()
