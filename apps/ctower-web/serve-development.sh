#!/usr/bin/env bash
# Serve the company-creation wizard against the local development instance.
#
# Two credentials, and they are not the same thing.
#
# The operator credential is resolved from the Secret Service reference the
# instance already uses and handed to the Vite process as an environment value
# for the life of that process. It is never written to a file, never passed as
# an argument, and never reaches the browser: the browser calls its own origin
# at `/v1/...` and this server's proxy attaches the credential.
#
# That makes the port itself operator authority for anyone who can reach it, and
# a tailnet bind is reachable by every host on the tailnet. So the server also
# mints a session token, prints it once below, and admits no API-bound request
# without it. The browser holds that token and sends it; the proxy checks it and
# strips it. It is admission to this process only — the API never sees it and it
# grants nothing there.
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
export CTOWER_WEB_SESSION_TOKEN="${CTOWER_WEB_SESSION_TOKEN:-$(openssl rand -hex 16)}"

printf '\n  Session token for http://%s:%s — paste it once in the browser:\n\n    %s\n\n' \
  "${CTOWER_WEB_HOST}" "${CTOWER_WEB_PORT}" "${CTOWER_WEB_SESSION_TOKEN}"

cd "${boundary}"
exec "${boundary}/node_modules/.bin/vite" --host "${CTOWER_WEB_HOST}" --port "${CTOWER_WEB_PORT}"
