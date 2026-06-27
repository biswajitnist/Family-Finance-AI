#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""
OLLAMA_PID=""

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export FINANCE_DATABASE_URL="sqlite:///$ROOT_DIR/backend/data/finance.db"
export FINANCE_UPLOADS_DIR="$ROOT_DIR/data/uploads"
export FINANCE_PROCESSED_DIR="$ROOT_DIR/data/processed"
export FINANCE_REPORTS_DIR="$ROOT_DIR/data/reports"
export FINANCE_CHROMA_DIR="$ROOT_DIR/data/chroma"
export FINANCE_MARKET_CREDENTIALS_FILE="$ROOT_DIR/data/market_credentials.json"

cleanup() {
  trap - EXIT INT TERM
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$OLLAMA_PID" ]] && kill "$OLLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

if [[ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
  echo "Backend environment is missing."
  echo "Run ./scripts/setup_dev.sh once, then start this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "Frontend dependencies are missing."
  echo "Run ./scripts/setup_dev.sh once, then start this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "Starting Ledger Local..."
if command -v ollama >/dev/null 2>&1 &&
  ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Starting Ollama..."
  ollama serve >/tmp/ledger-local-ollama.log 2>&1 &
  OLLAMA_PID=$!
fi
"$ROOT_DIR/scripts/run_backend.sh" &
BACKEND_PID=$!
"$ROOT_DIR/scripts/run_frontend.sh" &
FRONTEND_PID=$!

for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 &&
    curl -fsS http://localhost:5173 >/dev/null 2>&1; then
    echo
    echo "Ledger Local is live at http://localhost:5173"
    open http://localhost:5173
    wait
    exit 0
  fi

  if ! kill -0 "$BACKEND_PID" 2>/dev/null ||
    ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo
    echo "A server stopped during startup. Review the messages above."
    read -r -p "Press Enter to close..."
    exit 1
  fi
  sleep 1
done

echo
echo "The servers did not become ready within 60 seconds."
read -r -p "Press Enter to close..."
exit 1
