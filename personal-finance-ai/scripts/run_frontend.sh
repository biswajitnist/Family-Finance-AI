#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${LEDGER_HOST:-127.0.0.1}"
PORT="${LEDGER_FRONTEND_PORT:-5173}"
exec npm --prefix "$ROOT_DIR/frontend" run dev -- --host "$HOST" --port "$PORT"
