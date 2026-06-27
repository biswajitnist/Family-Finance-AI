#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
DIST_DIR="$ROOT_DIR/release"
BUILD_DIR="$ROOT_DIR/build/pyinstaller"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script builds the macOS .app package and must run on macOS."
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Development environment is missing. Run scripts/setup_dev.sh first."
  exit 1
fi

if ! "$VENV_DIR/bin/python" -c "import PyInstaller" 2>/dev/null; then
  echo "PyInstaller is missing. Install it with:"
  echo "  $VENV_DIR/bin/pip install -r packaging/requirements-build.txt"
  exit 1
fi

echo "Building production frontend..."
npm --prefix "$ROOT_DIR/frontend" run build

echo "Creating clean macOS application bundle..."
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

"$VENV_DIR/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --workpath "$BUILD_DIR" \
  --distpath "$DIST_DIR" \
  "$ROOT_DIR/packaging/ledger_local.spec"

APP_PATH="$DIST_DIR/Ledger Local.app"
ZIP_PATH="$DIST_DIR/Ledger-Local-macOS-arm64.zip"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Build failed: application bundle was not created."
  exit 1
fi

echo "Verifying that private runtime data was not packaged..."
if find "$APP_PATH" -type f \( \
  -name "finance.db" -o \
  -name "market_credentials.json" -o \
  -name "provider_secret.key" \
\) | grep -q .; then
  echo "Build stopped: private runtime data was found inside the application."
  exit 1
fi

ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"

echo
echo "Created:"
echo "  $APP_PATH"
echo "  $ZIP_PATH"
echo
echo "This unsigned build may require Control-click > Open on first launch."
