#!/usr/bin/env bash
# Restore the known-good provider if the SRE Agent has not already repaired it.

set -euo pipefail

source "$(dirname "$0")/_sre-env.sh"

echo "==> Restoring BUILDINGASSIST_OPERATIONS_SOURCE=simulator on ${BACKEND_APP}"
az containerapp update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$BACKEND_APP" \
  --set-env-vars BUILDINGASSIST_OPERATIONS_SOURCE=simulator \
  --output none

REVISION=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$BACKEND_APP" \
  --query properties.latestRevisionName \
  --output tsv)
wait_for_revision "$REVISION"
HTTP_STATUS=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "${BACKEND_URL}/healthz" || true)

if [[ "$HTTP_STATUS" != "200" ]]; then
  echo "ERROR: Expected HTTP 200 after the healthy revision became ready; got ${HTTP_STATUS}." >&2
  exit 1
fi

echo "  Healthy revision: ${REVISION}"
echo "  Backend health  : HTTP ${HTTP_STATUS} (expected 200)"
echo "  Frontend        : ${FRONTEND_URL}"