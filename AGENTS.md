# AGENTS.md

## Cursor Cloud specific instructions

Ledger is a self-hosted personal finance dashboard: a Python/FastAPI backend
(`backend/`), a React + Vite + TypeScript frontend (`frontend/`), and an optional
Tauri desktop shell (`desktop/`). Data is stored in local SQLite files
(`backend/ledger.db`, `backend/budgets.db`) that are auto-created on first run — no
database service to provision. See `README.md` ("Running from source") and
`CONTRIBUTING.md` for the canonical commands; notes below are only the non-obvious
bits for working in this environment.

### Services and how to run them

The backend Python venv lives at `backend/.venv` (created by the update script).
Always activate it before running backend commands: `source backend/.venv/bin/activate`.

- Backend (required): `cd backend && source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`. Health check: `http://127.0.0.1:8000/health`. API docs: `http://127.0.0.1:8000/docs`.
- Frontend dev server (required for dev): `cd frontend && npm run dev` → Vite on `http://localhost:5173`, which proxies `/api` to the backend on `:8000`. Use `:5173` during development for hot reload.
- Single-port mode (alternative): `cd frontend && npm run build`, then the backend serves the built SPA from `frontend/dist` at `http://127.0.0.1:8000`. If you see JSON/a blank page at `:8000` instead of the UI, the frontend has not been built.

Both dev servers are typically run in the background (e.g. tmux sessions
`ledger-backend` and `ledger-frontend`).

### Env / secrets

- `backend/.env` (gitignored) is required. It is created from `backend/.env.example`. The only value needed to boot is `ENCRYPTION_KEY` (a Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Do NOT rotate `ENCRYPTION_KEY` after a bank is linked — it decrypts stored Plaid tokens.
- The backend boots fine WITHOUT Plaid keys (BYOK/desktop design); `PlaidService.validate_config()` only logs a warning. Account creation and login work with no external credentials.
- Full end-to-end bank/transaction flows require Plaid **sandbox** credentials (`PLAID_CLIENT_ID`, `PLAID_SANDBOX_SECRET`, `PLAID_ENV=sandbox`). In Plaid sandbox, link any test institution with `user_good` / `pass_good`. Without these, Plaid Link cannot be exercised.
- Single-user model: the account is user id=1. Registration (`POST /api/auth/register`) only succeeds once; after that the app shows the login screen. To reset to first-run state, stop the backend and delete `backend/ledger.db*`.

### Lint / test / build

- Backend tests: `cd backend && source .venv/bin/activate && pytest tests/` (222 tests, all passing).
- Backend format/lint/types: `black .`, `flake8 .`, `mypy .` (config in `backend/pyproject.toml`).
- Frontend build: `cd frontend && npm run build` (passes).
- Frontend lint: `cd frontend && npm run lint`. NOTE: this runs ESLint with `--max-warnings 0`, and `main` currently has 14 pre-existing warnings (0 errors), so the lint command exits non-zero out of the box. This is a repo baseline, not an environment problem — do not "fix" it as part of unrelated work.

### System dependency note

The base image lacks `python3.12-venv`; it must be installed (via apt) before
`python3 -m venv` works. This is handled during environment setup, not by the
update script.
