#!/usr/bin/env bash
# Serve the company-creation wizard against the local development instance.
#
# The operator credential is resolved from the Secret Service reference the
# instance already uses and handed to the Vite process as an environment value
# for the life of that process. It is never written to a file, never passed as
# an argument, and never reaches the browser: the browser calls its own origin
# at `/api/...` and this server's proxy attaches the credential.
#
#   apps/ctower-web/serve-development.sh
#   CTOWER_WEB_HOST=100.84.252.114 CTOWER_WEB_PORT=3141 apps/ctower-web/serve-development.sh
set -euo pipefail

boundary="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
runtime="${CTOWER_RUNTIME_ROOT:-${HOME}/.local/share/ctower-development/runtime}"

export CTOWER_WEB_API_ORIGIN="${CTOWER_WEB_API_ORIGIN:-http://127.0.0.1:8091}"
export CTOWER_WEB_HOST="${CTOWER_WEB_HOST:-127.0.0.1}"
export CTOWER_WEB_PORT="${CTOWER_WEB_PORT:-3141}"
export CTOWER_WEB_API_TOKEN="$(
  "${runtime}/venv/bin/python" -c \
    'from ctower_api.development_secrets import load_secret; print(load_secret("secret-service:ctower-development/operator"), end="")'
)"

cd "${boundary}"
exec "${boundary}/node_modules/.bin/vite" --host "${CTOWER_WEB_HOST}" --port "${CTOWER_WEB_PORT}"
