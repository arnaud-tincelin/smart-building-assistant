#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec uv run --frozen --project "$ROOT/src/backend" python "$ROOT/scripts/demo_config.py" break "$@"