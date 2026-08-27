"""MCP tools for the fictional Contoso building-operations simulator."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .agent_policy import ACTION_MCP_TOOLS, READ_ONLY_MCP_TOOLS
from .building_operations import operations
from .config import settings

READ_ONLY_TOOLS = READ_ONLY_MCP_TOOLS
ACTION_TOOLS = ACTION_MCP_TOOLS

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

mcp_server = MCPServer(
    name="contoso-building-operations",
    title="Contoso Building Operations (simulated)",
    instructions=(
        "All telemetry and actions are fictional demo data. Use building IDs returned by "
        "list_buildings. Never present simulated changes as real-world operations."
    ),
)


@mcp_server.tool(annotations=_READ_ONLY, structured_output=True)
def list_buildings() -> dict[str, Any]:
    """List buildings available in the simulated operations platform."""
    return {"simulation": True, "buildings": operations.list_buildings()}


@mcp_server.tool(annotations=_READ_ONLY, structured_output=True)
def get_building_information(building_id: str) -> dict[str, Any]:
    """Get authoritative metadata, specificities, zones, and policy for a building."""
    return {
        "simulation": True,
        "building": operations.get_building_information(building_id),
    }


@mcp_server.tool(annotations=_READ_ONLY, structured_output=True)
def get_building_data(building_id: str) -> dict[str, Any]:
    """Get time-stamped telemetry, zone measurements, and active alerts for a building."""
    return {
        "simulation": True,
        "data": operations.get_building_data(building_id),
    }


@mcp_server.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
def create_work_order(
    building_id: str,
    title: str,
    reason: str,
    priority: str = "medium",
) -> dict[str, Any]:
    """Create a fictional maintenance work order in the simulator."""
    return operations.create_work_order(building_id, title, reason, priority)


@mcp_server.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
def set_hvac_setpoint(
    building_id: str,
    zone_id: str,
    temperature_c: float,
    duration_minutes: int,
    reason: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Apply a temporary fictional HVAC setpoint after explicit confirmation."""
    return operations.set_hvac_setpoint(
        building_id,
        zone_id,
        temperature_c,
        duration_minutes,
        reason,
        confirmed,
    )


mcp_http_app = mcp_server.streamable_http_app(
    streamable_http_path="/",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=settings.mcp_allowed_hosts_list,
        allowed_origins=settings.mcp_allowed_origins_list,
    ),
)