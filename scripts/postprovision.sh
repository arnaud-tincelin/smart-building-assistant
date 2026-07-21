#!/bin/sh
# azd postprovision hook — create the BuildingAssist Foundry **prompt agent** so it
# shows up in the project's Agents list. Idempotent: safe to re-run on every `azd up`.
#
# Step 1 (this hook): a plain prompt agent (model + instructions, no tools).
# Step 2 (later): Foundry IQ grounding — a file_search tool over the sample-doc
# vector store built by scripts/setup_foundry_knowledge.py.
set -eu

ROOT="$(pwd)"
export SAMPLE_DOCS_DIR="$ROOT/sample-docs"

echo "==> Post-provision: Foundry prompt agent setup"
cd "$ROOT/src/backend"
uv run python "$ROOT/scripts/setup_foundry_agent.py"

echo
echo "Frontend: ${SERVICE_FRONTEND_URL:-<pending>}"
echo "Backend : ${SERVICE_BACKEND_URL:-<pending>}"
echo "Foundry : ${AZURE_AI_PROJECT_ENDPOINT:-<pending>}"
echo
echo "SRE Agent GitHub connector + incident runbook are configured in the agent"
echo "Builder (data plane) — see docs/sre-agent.md."
