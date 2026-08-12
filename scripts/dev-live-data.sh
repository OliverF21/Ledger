#!/usr/bin/env bash
# Run the backend against the desktop app's live DBs (Application Support),
# with hot reload. Use Vite separately for instant frontend updates:
#   cd frontend && npm run dev   →  http://localhost:5173
#
# IMPORTANT: quit the Ledger desktop app first. Two writers on one SQLite
# file can lock or corrupt it.
#
# On startup the server prints:
#   [LEDGER_USE_APPDATA] Using desktop DBs: ...
#   [DB] ledger:  sqlite:////Users/.../Application%20Support/Ledger/ledger.db
# If you still see backend/ledger.db in that line, you're on the old DB.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

if [[ -z "${VIRTUAL_ENV:-}" && -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export LEDGER_USE_APPDATA=1
# Clear any shell-exported DB URLs so they cannot shadow app-data.
unset DATABASE_URL BUDGETS_DATABASE_URL ENCRYPTION_KEY 2>/dev/null || true

APP="${HOME}/Library/Application Support/Ledger"
if [[ "$(uname -s)" == "Darwin" && ! -f "${APP}/ledger.db" ]]; then
  echo "No desktop ledger.db at: ${APP}/ledger.db"
  echo "Open the Ledger desktop app once first, then re-run."
  exit 1
fi

echo "Using desktop app data (LEDGER_USE_APPDATA=1)."
echo "Quit Ledger desktop before continuing. API: http://127.0.0.1:8000"
echo "Frontend hot reload: cd frontend && npm run dev → http://localhost:5173"
echo "Confirm the uvicorn log shows Application Support (not backend/ledger.db)."
echo

exec python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
