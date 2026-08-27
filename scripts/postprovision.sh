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
echo "==> Post-provision: SRE Agent incident workflow setup"
cd "$ROOT"
python3 "$ROOT/scripts/setup_sre_agent.py"

echo
echo "Frontend: ${SERVICE_FRONTEND_URL:-<pending>}"
echo "Backend : ${SERVICE_BACKEND_URL:-<pending>}"
echo "Foundry : ${AZURE_AI_PROJECT_ENDPOINT:-<pending>}"
echo
echo "SRE Agent workflow details: docs/sre-agent.md"
