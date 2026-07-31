#!/usr/bin/env bash
set -euo pipefail

: "${PORT:=10000}"
export PORT

# A API usa um soquete Unix, sem porta TCP. Assim o Render só detecta e expõe
# o servidor web público iniciado ao final deste script.
api_socket=/tmp/consulta-loa-api.sock
rm -f "$api_socket"

HOSTNAME=127.0.0.1 PORT=3000 node /app/web/server.js &
web_pid=$!
api_pid=""
trap 'kill "$web_pid" "$api_pid" 2>/dev/null || true' EXIT INT TERM

uvicorn loa_api.main:app --uds "$api_socket" &
api_pid=$!

exec node /app/scripts/render_proxy.mjs
