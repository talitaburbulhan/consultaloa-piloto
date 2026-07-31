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

for _ in $(seq 1 50); do
  [ -S "$api_socket" ] && break
  if ! kill -0 "$api_pid" 2>/dev/null; then
    wait "$api_pid"
    exit 1
  fi
  sleep 0.1
done
[ -S "$api_socket" ] || exit 1

exec node /app/scripts/render_proxy.mjs
