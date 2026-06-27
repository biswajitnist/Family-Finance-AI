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
export LEDGER_HOST="0.0.0.0"
export LEDGER_BACKEND_PORT="${LEDGER_BACKEND_PORT:-8000}"
export LEDGER_FRONTEND_PORT="${LEDGER_FRONTEND_PORT:-5173}"

cleanup() {
  trap - EXIT INT TERM
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$OLLAMA_PID" ]] && kill "$OLLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

detect_lan_ip() {
  for interface in en0 en1 en2; do
    ipconfig getifaddr "$interface" 2>/dev/null && return 0
  done
  ifconfig 2>/dev/null | awk '
    /inet / && $2 != "127.0.0.1" && $2 ~ /^(10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)/ {
      print $2
      exit
    }
  ' && return 0
  route get default 2>/dev/null | awk '/interface:/{print $2; exit}' | while read -r interface; do
    ipconfig getifaddr "$interface" 2>/dev/null
  done
}

LAN_IP="$(detect_lan_ip | head -n 1)"
if [[ -z "$LAN_IP" ]]; then
  echo "Could not detect this Mac's LAN IP."
  echo "Make sure Wi-Fi or Ethernet is connected, then try again."
  read -r -p "Press Enter to close..."
  exit 1
fi

export FINANCE_FRONTEND_ORIGIN="http://$LAN_IP:$LEDGER_FRONTEND_PORT"
export VITE_API_URL="http://$LAN_IP:$LEDGER_BACKEND_PORT/api"

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

echo "Starting Ledger Local for LAN access..."
echo "Backend API:  $VITE_API_URL"
echo "Frontend URL: http://$LAN_IP:$LEDGER_FRONTEND_PORT"
echo
echo "Use that Frontend URL from another device on the same Wi-Fi/LAN."
echo

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
  if curl -fsS "http://127.0.0.1:$LEDGER_BACKEND_PORT/api/health" >/dev/null 2>&1 &&
    curl -fsS "http://127.0.0.1:$LEDGER_FRONTEND_PORT" >/dev/null 2>&1; then
    echo
    echo "Ledger Local is live on your LAN:"
    echo "http://$LAN_IP:$LEDGER_FRONTEND_PORT"
    open "http://$LAN_IP:$LEDGER_FRONTEND_PORT"
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
