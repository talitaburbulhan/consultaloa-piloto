#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:=sqlite:////var/data/loa.db}"
: "${STORAGE_DIR:=/var/data}"
: "${SOURCE_DIR:=/var/data/dados}"
: "${PORT:=10000}"

export DATABASE_URL STORAGE_DIR SOURCE_DIR PORT

if [[ ! -f /var/data/loa.db ]]; then
  echo "Banco do piloto ainda não está no disco persistente. O serviço iniciará em modo de preparação; antes de liberar o endereço público, envie loa.db e a pasta dados para /var/data e reinicie o serviço."
fi

exec uvicorn loa_api.main:app --host 0.0.0.0 --port "$PORT"
