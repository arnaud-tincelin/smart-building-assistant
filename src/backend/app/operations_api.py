"""REST API for the fictional Contoso building-operations simulator."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .building_operations import operations
from .models import HvacSetpointRequest, WorkOrderRequest

router = APIRouter(prefix="/operations", tags=["building operations"])


@router.get(
    "/buildings",
    operation_id="listBuildings",
    summary="List buildings",
)
def list_buildings() -> dict[str, Any]:
    """List buildings available in the simulated operations platform."""
    return {"simulation": True, "buildings": operations.list_buildings()}


@router.get(
    "/buildings/{building_id}/information",
    operation_id="getBuildingInformation",
    summary="Get building information",
)
def get_building_information(building_id: str) -> dict[str, Any]:
    """Get authoritative metadata, specificities, zones, and policy for a building."""
    return {"simulation": True, "building": operations.get_building_information(building_id)}


@router.get(
    "/buildings/{building_id}/data",
    operation_id="getBuildingData",
    summary="Get current building data",
)
def get_building_data(building_id: str) -> dict[str, Any]:
    """Get time-stamped telemetry, zone measurements, and active alerts for a building."""
    return {"simulation": True, "data": operations.get_building_data(building_id)}


@router.post(
    "/work-orders",
    operation_id="createWorkOrder",
    summary="Create a work order",
)
def create_work_order(request: WorkOrderRequest) -> dict[str, Any]:
    """Create a fictional maintenance work order in the simulator."""
    return operations.create_work_order(
        request.building_id,
        request.title,
        request.reason,
        request.priority,
    )


@router.post(
    "/hvac-setpoints",
    operation_id="setHvacSetpoint",
    summary="Set a temporary HVAC setpoint",
)
def set_hvac_setpoint(request: HvacSetpointRequest) -> dict[str, Any]:
    """Apply a temporary fictional HVAC setpoint after explicit confirmation."""
    return operations.set_hvac_setpoint(
        request.building_id,
        request.zone_id,
        request.temperature_c,
        request.duration_minutes,
        request.reason,
        request.confirmed,
    )
