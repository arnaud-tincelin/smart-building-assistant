#!/usr/bin/env bash
# Post-create setup for the BuildingAssist demo devcontainer.
#  - Python backend  (src/backend)  managed with uv
#  - TypeScript front (src/frontend) managed with npm
# No Docker daemon: images are built remotely by `azd` using ACR remote build.
set -euo pipefail

echo "==> Tool versions"
uv --version
node --version
npm --version

# ---- Backend (Python + uv) ----
export UV_PYTHON=3.12
if [ -f "src/backend/pyproject.toml" ]; then
  echo "==> Backend: uv sync (src/backend)"
  (cd src/backend && uv sync)
elif [ -f "src/backend/requirements.txt" ]; then
  echo "==> Backend: uv venv + install (src/backend/requirements.txt)"
  (cd src/backend && uv venv && uv pip install -r requirements.txt)
else
  echo "==> Backend: no manifest yet — skipping"
fi

# ---- Frontend (TypeScript + npm) ----
if [ -f "src/frontend/package.json" ]; then
  echo "==> Frontend: npm install (src/frontend)"
  (cd src/frontend && npm install)
else
  echo "==> Frontend: no package.json yet — skipping"
fi

echo "==> Azure toolchain"
az version --output table || true
az bicep version || true
azd version || true

echo "==> Devcontainer ready (backend: uv, frontend: npm, images via ACR remote build)."
