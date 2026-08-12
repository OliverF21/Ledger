#!/usr/bin/env bash
# Run the backend against the desktop app's live DBs (Application Support),
# with hot reload. Use Vite separately for instant frontend updates:
#   cd frontend && npm run dev   →  http://localhost:5173
#
# IMPORTANT: quit the Ledger desktop app first. Two writers on one SQLite
# file can lock or corrupt it.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

if [[ -z "${VIRTUAL_ENV:-}" && -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export LEDGER_USE_APPDATA=1

echo "Using desktop app data (LEDGER_USE_APPDATA=1)."
echo "Quit Ledger desktop before continuing. API: http://127.0.0.1:8000"
echo "Frontend hot reload: cd frontend && npm run dev → http://localhost:5173"
echo

exec python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
