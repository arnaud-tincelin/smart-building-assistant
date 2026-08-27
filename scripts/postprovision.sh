#!/bin/sh
# azd postprovision hook — sync Foundry IQ knowledge, then create or update the
# BuildingAssist prompt agent with Knowledge Base and operations MCP tools.
set -eu

ROOT="$(pwd)"
export SAMPLE_DOCS_DIR="$ROOT/sample-docs"

echo "==> Post-provision: Foundry IQ Knowledge Base setup"
cd "$ROOT/src/backend"
uv run python "$ROOT/scripts/setup_foundry_iq.py"

echo
echo "==> Post-provision: Foundry prompt agent setup"
uv run python "$ROOT/scripts/setup_foundry_agent.py"

echo
echo "Frontend: ${SERVICE_FRONTEND_URL:-<pending>}"
echo "Backend : ${SERVICE_BACKEND_URL:-<pending>}"
echo "Foundry : ${AZURE_AI_PROJECT_ENDPOINT:-<pending>}"
echo
echo "SRE Agent GitHub connector + incident runbook are configured in the agent"
echo "Builder (data plane) — see docs/sre-agent.md."
