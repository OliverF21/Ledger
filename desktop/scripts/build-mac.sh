#!/usr/bin/env bash
# Full macOS build pipeline for the Ledger desktop app.
#
#   1. build the frontend (frontend/dist)
#   2. bundle the backend with PyInstaller (backend/dist/ledger-backend)
#   3. build the Tauri .app (unsigned)
#   4. wrap it in a .dmg via hdiutil
#
# Prereqs: Node + npm, Rust (rustup), Python 3.11+ with a venv at backend/venv.
# Unsigned output — see README "First launch (macOS)".
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export PATH="$HOME/.cargo/bin:$PATH"

echo "==> [1/4] frontend build"
cd "$ROOT/frontend"
[ -d node_modules ] || npm ci
npm run build

echo "==> [2/4] backend bundle (PyInstaller)"
cd "$ROOT/backend"
if [ ! -x venv/bin/python ]; then
  python3 -m venv venv
  ./venv/bin/pip install -q -r requirements.txt
fi
./venv/bin/pip install -q pyinstaller
rm -rf build dist
./venv/bin/pyinstaller ledger.spec --noconfirm

echo "==> [3/4] Tauri app (.app only; .dmg made separately)"
cd "$ROOT/desktop"
[ -d node_modules ] || npm install
# Release builds (signed auto-update artifacts) when the updater signing key is
# provided; otherwise a plain unsigned build with no updater config.
#   TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.ledger/updater.key)" \
#   TAURI_SIGNING_PRIVATE_KEY_PASSWORD="" bash desktop/scripts/build-mac.sh
if [ -n "${TAURI_SIGNING_PRIVATE_KEY:-}" ]; then
  echo "    (release: signing updater artifacts via tauri.release.conf.json)"
  npx tauri build --bundles app --config src-tauri/tauri.release.conf.json
else
  npx tauri build --bundles app
fi

echo "==> [4/4] .dmg"
bash "$ROOT/desktop/scripts/make-dmg.sh"

echo "==> done"
