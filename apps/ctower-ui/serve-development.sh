#!/usr/bin/env bash
# Serve the read-only phase-1 surface against the local shadow instance.
#
# The operator credential is resolved from the Secret Service reference the
# instance already uses and handed to the Node process as an environment value
# for the life of that process. It is never written to a file, never passed as
# an argument, and never reaches the browser: every read is server-side.
#
#   apps/ctower-ui/serve-development.sh          # production server on :3117
#   CTOWER_UI_PORT=3117 apps/ctower-ui/serve-development.sh
set -euo pipefail

boundary="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository="$(cd -- "${boundary}/../.." && pwd -P)"
runtime="${CTOWER_RUNTIME_ROOT:-${HOME}/.local/share/ctower-development/runtime}"

export CTOWER_UI_API_BASE_URL="${CTOWER_UI_API_BASE_URL:-http://127.0.0.1:8091}"
export CTOWER_UI_INSTANCE_LABEL="${CTOWER_UI_INSTANCE_LABEL:-shadow}"
export CTOWER_UI_INSTANCE_REVISION="${CTOWER_UI_INSTANCE_REVISION:-$(git -C "${repository}" rev-parse --short=8 HEAD)}"
export CTOWER_UI_API_TOKEN="$(
  "${runtime}/venv/bin/python" -c \
    'from ctower_api.development_secrets import load_secret; print(load_secret("secret-service:ctower-development/operator"), end="")'
)"

cd "${boundary}"
exec "${boundary}/node_modules/.bin/next" start \
  --port "${CTOWER_UI_PORT:-3117}" \
  --hostname "${CTOWER_UI_HOST:-127.0.0.1}"
