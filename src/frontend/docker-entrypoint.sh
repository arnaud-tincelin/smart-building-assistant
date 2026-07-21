#!/bin/sh
# Render the runtime config for the static frontend from the BACKEND_URL env var.
# nginx:alpine executes scripts in /docker-entrypoint.d/ before launching nginx.
set -eu

: "${BACKEND_URL:=}"

export BACKEND_URL
envsubst '${BACKEND_URL}' \
  < /usr/share/nginx/html/config.template.js \
  > /usr/share/nginx/html/config.js

echo "buildingassist: config.js rendered with BACKEND_URL=${BACKEND_URL:-<empty>}"
