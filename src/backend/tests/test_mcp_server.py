from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from mcp.types import LATEST_PROTOCOL_VERSION

from app.main import app
from app.mcp_server import ACTION_TOOLS, READ_ONLY_TOOLS, mcp_server


def test_mcp_server_exposes_read_and_action_tools() -> None:
    tools = asyncio.run(mcp_server.list_tools())
    tools_by_name = {tool.name: tool for tool in tools}

    assert set(tools_by_name) == set(READ_ONLY_TOOLS + ACTION_TOOLS)
    assert tools_by_name["get_building_information"].annotations.read_only_hint is True
    assert tools_by_name["set_hvac_setpoint"].annotations.destructive_hint is True


def test_mcp_streamable_http_endpoint_initializes() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/mcp/",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "buildingassist-tests",
                        "version": "1.0",
                    },
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "contoso-building-operations"