#!/usr/bin/env bash
set -euo pipefail

: "${PORT:=10000}"
export PORT

# A interface precisa iniciar primeiro: o Render deve expor a porta da aplicação
# web, e não a porta interna da API.
node /app/web/server.js &
web_pid=$!
api_pid=""
trap 'kill "$web_pid" "$api_pid" 2>/dev/null || true' EXIT INT TERM

sleep 2
uvicorn loa_api.main:app --host 127.0.0.1 --port 8001 &
api_pid=$!

wait -n "$web_pid" "$api_pid"
