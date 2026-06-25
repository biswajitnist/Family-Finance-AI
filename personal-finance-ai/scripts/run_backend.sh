#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${LEDGER_HOST:-127.0.0.1}"
PORT="${LEDGER_BACKEND_PORT:-8000}"
cd "$ROOT_DIR/backend"
exec "$ROOT_DIR/.venv/bin/uvicorn" app.main:app --reload --host "$HOST" --port "$PORT"
