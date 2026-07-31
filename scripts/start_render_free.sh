#!/usr/bin/env bash
set -euo pipefail

: "${PORT:=10000}"
export PORT

uvicorn loa_api.main:app --host 127.0.0.1 --port 10001 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM

exec node /app/web/server.js
