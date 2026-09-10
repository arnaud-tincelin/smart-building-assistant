#!/usr/bin/env bash

if [[ -n "${_BUILDINGASSIST_SRE_ENV_LOADED:-}" ]]; then
  return 0
fi
_BUILDINGASSIST_SRE_ENV_LOADED=1

azd_value() {
  azd env get-value "$1" 2>/dev/null
}

if ! command -v azd >/dev/null 2>&1; then
  echo "ERROR: azd is required to resolve the deployed demo environment." >&2
  exit 1
fi

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-$(azd_value AZURE_RESOURCE_GROUP)}"
BACKEND_APP="${BACKEND_CONTAINER_APP_NAME:-$(azd_value BACKEND_CONTAINER_APP_NAME)}"
BACKEND_URL="${SERVICE_BACKEND_URL:-$(azd_value SERVICE_BACKEND_URL)}"
FRONTEND_URL="${SERVICE_FRONTEND_URL:-$(azd_value SERVICE_FRONTEND_URL)}"

if [[ -z "$RESOURCE_GROUP" || -z "$BACKEND_APP" || -z "$BACKEND_URL" || -z "$FRONTEND_URL" ]]; then
  echo "ERROR: SRE demo outputs are unavailable. Run 'azd provision' first." >&2
  exit 1
fi

wait_for_revision() {
  local revision="$1"
  local ready_revision

  for _ in {1..24}; do
    ready_revision=$(az containerapp show \
      --resource-group "$RESOURCE_GROUP" \
      --name "$BACKEND_APP" \
      --query properties.latestReadyRevisionName \
      --output tsv)
    if [[ "$ready_revision" == "$revision" ]]; then
      return 0
    fi
    sleep 5
  done

  echo "ERROR: Revision ${revision} did not become ready within two minutes." >&2
  return 1
}