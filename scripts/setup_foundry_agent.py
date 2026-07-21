"""Post-provision setup for the BuildingAssist Foundry **prompt agent**.

Runs from the azd `postprovision` hook. Creates (idempotently, by name) a Foundry
**prompt agent** — a model deployment + instructions — so it shows up in the
project's **Agents** list and can be exercised from the playground or the backend.

This is **step 1**: a plain agent with no tools. Foundry IQ grounding (a
``file_search`` tool over the sample-doc vector store) is added in step 2.

Auth uses ``DefaultAzureCredential`` — locally this resolves to the azd/az login,
and the developer principal is granted ``Azure AI User`` on the Foundry account by
``infra/modules/rbac.bicep``.

Environment (provided by azd as infra outputs):
- ``AZURE_AI_PROJECT_ENDPOINT`` — the Foundry project endpoint.

Optional:
- ``BUILDINGASSIST_AGENT_NAME`` — agent name (default ``buildingassist-agent``).
- ``AZURE_AI_MODEL_DEPLOYMENT_NAME`` / ``AZURE_AI_MODEL_DEPLOYMENT`` /
  ``BUILDINGASSIST_MODEL_DEPLOYMENT`` — the model deployment the agent reasons with
  (default ``gpt-4.1-mini``).
"""

from __future__ import annotations

import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential

AGENT_NAME = os.environ.get("BUILDINGASSIST_AGENT_NAME", "buildingassist-agent")
MODEL_DEPLOYMENT = (
    os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT")
    or os.environ.get("BUILDINGASSIST_MODEL_DEPLOYMENT")
    or "gpt-4.1-mini"
)

INSTRUCTIONS = (
    "You are BuildingAssist, an assistant for Contoso Energy's smart buildings. "
    "Answer questions about building energy use concisely and factually. If you "
    "don't have the data, say so plainly."
)


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


def _ensure_agent(client: AIProjectClient) -> None:
    """Create the prompt agent, or add a version only when the definition changed."""
    desired = PromptAgentDefinition(model=MODEL_DEPLOYMENT, instructions=INSTRUCTIONS)
    current = _latest_definition(client)

    if current is not None:
        want = desired.as_dict()
        if current.get("model") == want.get("model") and current.get(
            "instructions"
        ) == want.get("instructions"):
            print(f"Reusing prompt agent {AGENT_NAME!r} (unchanged).")
            return
        print(f"Updating prompt agent {AGENT_NAME!r} (definition changed).")
    else:
        print(f"Creating prompt agent {AGENT_NAME!r} on {MODEL_DEPLOYMENT}.")

    version = client.agents.create_version(
        agent_name=AGENT_NAME,
        definition=desired,
        description="Contoso Energy smart-building assistant (BuildingAssist).",
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
