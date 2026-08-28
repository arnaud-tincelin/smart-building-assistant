"""Post-provision setup for the BuildingAssist Foundry prompt agent.

Runs from the azd ``postprovision`` hook after knowledge sync. Creates or updates
the visible prompt agent with Model Router, Foundry IQ, and the
simulated building-operations MCP tools.

Auth uses ``DefaultAzureCredential`` — locally this resolves to the azd/az login,
and the developer principal is granted ``Azure AI User`` on the Foundry account by
``infra/modules/rbac.bicep``.

Environment (provided by azd as infra outputs):
- ``AZURE_AI_PROJECT_ENDPOINT`` — the Foundry project endpoint.

Optional:
- ``BUILDINGASSIST_AGENT_NAME`` — agent name (default ``buildingassist-agent``).
- ``AZURE_AI_MODEL_DEPLOYMENT_NAME`` / ``AZURE_AI_MODEL_DEPLOYMENT`` /
  ``BUILDINGASSIST_MODEL_DEPLOYMENT`` — the model deployment the agent reasons with
    (default ``model-router``).
- ``BUILDINGASSIST_MCP_SERVER_URL`` — APIM-hosted Streamable HTTP MCP endpoint.
- ``BUILDINGASSIST_MCP_CONNECTION`` — Foundry project connection that stores the
    APIM subscription header (default ``buildingassist-operations``).
"""

from __future__ import annotations

import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    MCPTool,
    MCPToolFilter,
    MCPToolRequireApproval,
    PromptAgentDefinition,
)
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential

from app.agent_policy import (
    ACTION_MCP_TOOLS,
    AGENT_INSTRUCTIONS,
    READ_ONLY_MCP_TOOLS,
)

AGENT_NAME = os.environ.get("BUILDINGASSIST_AGENT_NAME", "buildingassist-agent")
MODEL_DEPLOYMENT = (
    os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT")
    or os.environ.get("BUILDINGASSIST_MODEL_DEPLOYMENT")
    or "model-router"
)
MCP_SERVER_URL = os.environ.get("BUILDINGASSIST_MCP_SERVER_URL", "")
MCP_CONNECTION = os.environ.get(
    "BUILDINGASSIST_MCP_CONNECTION", "buildingassist-operations"
)
KNOWLEDGE_MCP_ENDPOINT = os.environ.get("BUILDINGASSIST_KNOWLEDGE_MCP_ENDPOINT", "")
KNOWLEDGE_CONNECTION = os.environ.get(
    "BUILDINGASSIST_KNOWLEDGE_CONNECTION", "buildingassist-knowledge"
)
MCP_TOOLS = READ_ONLY_MCP_TOOLS + ACTION_MCP_TOOLS


def _latest_definition(client: AIProjectClient) -> dict | None:
    """Return the latest version's definition dict, or None if the agent is new."""
    try:
        client.agents.get(AGENT_NAME)
    except ResourceNotFoundError:
        return None

    versions = client.agents.list_versions(AGENT_NAME, limit=1, order="desc")
    latest = next(iter(versions), None)
    if latest is None:
        return None
    definition = getattr(latest, "definition", None)
    if definition is None:
        return None
    return definition.as_dict() if hasattr(definition, "as_dict") else dict(definition)


def _build_tools() -> list:
    tools = []
    if KNOWLEDGE_MCP_ENDPOINT:
        tools.append(
            MCPTool(
                server_label="building_knowledge",
                server_description="Foundry IQ Knowledge Base for stable Contoso building facts.",
                server_url=KNOWLEDGE_MCP_ENDPOINT,
                allowed_tools=["knowledge_base_retrieve"],
                require_approval="never",
                project_connection_id=KNOWLEDGE_CONNECTION,
            )
        )
    else:
        print("No Foundry IQ Knowledge Base endpoint found; agent will be ungrounded.")

    if MCP_SERVER_URL:
        tools.append(
            MCPTool(
                server_label="building_operations",
                server_description=(
                    "Fictional current telemetry, alerts, and bounded actions "
                    "for Contoso buildings."
                ),
                server_url=MCP_SERVER_URL,
                allowed_tools=MCP_TOOLS,
                require_approval=MCPToolRequireApproval(
                    always=MCPToolFilter(tool_names=ACTION_MCP_TOOLS),
                    never=MCPToolFilter(tool_names=READ_ONLY_MCP_TOOLS),
                ),
                project_connection_id=MCP_CONNECTION,
            )
        )
    else:
        print("No MCP server URL found; agent will not have live operations tools.")
    return tools


def _ensure_agent(client: AIProjectClient) -> None:
    """Create the prompt agent, or add a version only when the definition changed."""
    desired = PromptAgentDefinition(
        model=MODEL_DEPLOYMENT,
        instructions=AGENT_INSTRUCTIONS,
        tools=_build_tools(),
        tool_choice="required",
    )
    current = _latest_definition(client)

    if current is not None:
        want = desired.as_dict()
        comparable_fields = ("model", "instructions", "tools", "tool_choice")
        if all(current.get(field) == want.get(field) for field in comparable_fields):
            print(f"Reusing prompt agent {AGENT_NAME!r} (unchanged).")
            return
        print(f"Updating prompt agent {AGENT_NAME!r} (definition changed).")
    else:
        print(f"Creating prompt agent {AGENT_NAME!r} on {MODEL_DEPLOYMENT}.")

    version = client.agents.create_version(
        agent_name=AGENT_NAME,
        definition=desired,
        description="Grounded smart-building assistant with simulated MCP operations.",
    )
    print(f"Registered {AGENT_NAME!r} version {getattr(version, 'version', '?')}.")


def main() -> int:
    endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        print("AZURE_AI_PROJECT_ENDPOINT is not set — skipping agent setup.", file=sys.stderr)
        return 0

    client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    _ensure_agent(client)
    print(f"BUILDINGASSIST_AGENT_NAME={AGENT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
