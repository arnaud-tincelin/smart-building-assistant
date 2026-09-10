#!/usr/bin/env bash
# Scenario 2: deploy an unsupported operations provider without changing the image.

set -euo pipefail

BAD_OPERATIONS_SOURCE="${BAD_OPERATIONS_SOURCE:-digital-twins-prod}"
if [[ "$BAD_OPERATIONS_SOURCE" == "simulator" ]]; then
  echo "ERROR: BAD_OPERATIONS_SOURCE must differ from the known-good value 'simulator'." >&2
  exit 1
fi

source "$(dirname "$0")/_sre-env.sh"

echo "==> Setting BUILDINGASSIST_OPERATIONS_SOURCE=${BAD_OPERATIONS_SOURCE} on ${BACKEND_APP}"
az containerapp update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$BACKEND_APP" \
  --set-env-vars "BUILDINGASSIST_OPERATIONS_SOURCE=${BAD_OPERATIONS_SOURCE}" \
  --output none

REVISION=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$BACKEND_APP" \
  --query properties.latestRevisionName \
  --output tsv)
wait_for_revision "$REVISION"
HTTP_STATUS=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "${BACKEND_URL}/healthz" || true)

if [[ "$HTTP_STATUS" != "503" ]]; then
  echo "ERROR: Expected HTTP 503 after the bad revision became ready; got ${HTTP_STATUS}." >&2
  exit 1
fi

echo
echo "  Broken revision: ${REVISION}"
echo "  Backend health : HTTP ${HTTP_STATUS} (expected 503)"
echo "  Frontend       : ${FRONTEND_URL}"
echo "  Alert marker   : config-availability"
echo
echo "The Sev1 alert evaluates every minute and routes to platform-config-operator."
echo "Manual reset: scripts/demo/fix-config.sh"