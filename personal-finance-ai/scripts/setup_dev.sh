#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"
npm --prefix "$ROOT_DIR/frontend" install

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

echo "Setup complete. Use scripts/run_backend.sh and scripts/run_frontend.sh."
echo "For OCR and Ollama verification, run scripts/setup_local_ai.sh."
