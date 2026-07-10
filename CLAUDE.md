# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Ledger** is an open-source-style personal finance management web app that connects to Plaid to pull live transactions from bank accounts and credit cards, categorizes spending, and provides dashboards for monitoring over time. Built for single-user use but structured with clean architecture suitable for open-sourcing.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL (SQLite for local dev fallback)
- **Frontend**: React + TypeScript + Vite, Tailwind CSS, Recharts for visualizations
- **Plaid SDK**: no SDK dependency — raw `requests`-based REST wrapper in `plaid_service.py`
- **Auth**: username/password account (single-user, id=1) created on first run; login issues a Fernet-signed session token (Bearer) with a TTL. Optional legacy `API_KEY` still accepted via `X-API-Key`. See `app/auth.py` + `routes/auth.py`.
- **Deployment**: Docker Compose locally; Railway or Fly.io for production
- **Scheduling**: APScheduler for periodic transaction syncs

## Architecture

### High-Level Data Flow
```
Plaid Link (frontend) 
  → create_link_token endpoint
  → exchange public_token for access_token
  → store encrypted access_token in DB (Item)
  → sync endpoint pulls transactions using Plaid's /transactions/sync
  → categorization rules engine applies overrides
  → dashboard queries aggregated transaction data
```

### Key Components

**Backend (`/backend`)**:
- **models.py**: SQLAlchemy ORM — `Item` (Plaid connection), `Account`, `Transaction`, `Category`, `CategoryRule`, `BalanceSnapshot`, `Security`, `Holding`, `InvestmentTransaction`
- **plaid_service.py**: raw `requests` Plaid REST wrapper — link token, token exchange, transaction sync, accounts, investments
- **sync_engine.py**: Incremental transaction sync logic using Plaid's cursor-based endpoint; `sync_investments()` upserts holdings/positions after each bank sync
- **categorization.py**: Rules engine for applying custom category overrides and detecting manual recategorizations
- **scheduler.py**: APScheduler background jobs for periodic syncs and balance snapshots
- **security.py**: Fernet encryption/decryption for Plaid access tokens at rest
- **routes/auth.py**: first-run register/login, session tokens
- **routes/proposals.py**: AI advisor proposals (MCP create, user apply/dismiss)
- **mcp_server/**: Claude Desktop MCP tools (read analytics, propose budgets)
- **routes/investments.py**: `GET /investments/summary|holdings|transactions|history`, `POST /investments/refresh`

**Frontend (`/frontend`)**:
- **src/components/PlaidLink.tsx**: Plaid Link integration using `react-plaid-link`
- **src/pages/Overview.tsx**: Main dashboard — net worth, spending KPIs, recent transactions
- **src/pages/Transactions.tsx**: Recent transactions feed with search/filter
- **src/pages/Spending.tsx**, **src/pages/Budgets.tsx**, **src/pages/Trends.tsx**: cash-flow, budget, and trend dashboards
- **src/pages/Investments.tsx**: dedicated portfolio tab (`#investments`) — KPI row, allocation donut, per-account holdings table, recent investment activity; manual refresh button hits `POST /api/investments/refresh`
- **src/hooks/useInvestments.ts**: `useInvestmentsSummary()`, `useInvestmentsHoldings()`, `useInvestmentTransactions(months)`
- **src/pages/Settings.tsx**: category rules, budget configuration, linked accounts
- **src/App.tsx**: hash-based routing (`window.location.hash`) — no router package
- **src/api/client.ts**: `apiFetch()` — attaches `Authorization: Bearer` session token

**Database Schema**:
- `users`: single-user app (just one record for now, but structured for future expansion)
- `items`: encrypted Plaid access tokens, item IDs, last sync cursors
- `accounts`: account metadata (name, balance, institution, account subtype)
- `transactions`: merchant, amount, date, category, pending flag, manual override flag
- `categories`: user-editable category definitions (inherits Plaid PFC taxonomy by default)
- `category_rules`: user-defined rules (merchant pattern → category override)
- `balance_snapshots`: daily snapshots of account balances for net worth tracking
- `budgets` / `proposals`: in separate `budgets.db` (see `budgets_db.py`), not in `models.py`
- `securities`: Plaid security metadata (ticker, name, type, close price) keyed by `plaid_security_id`
- `holdings`: position-level holdings per investment account (quantity, price, value, cost basis), unique per `(account_id, security_id)`
- `investment_transactions`: brokerage buy/sell/dividend/fee activity, separate from bank `transactions` (no categorization, not part of spending analytics)

## Development Setup

### Prerequisites
- Python 3.11+, Node.js 18+, Docker & Docker Compose
- Plaid dev account (free sandbox tier available)
- **ngrok** (`pip install ngrok`, in `requirements.txt`) — required for OAuth brokerages (Robinhood) on localhost with production Plaid keys; see `docs/PLAID_SETUP.md`

### Local Development Commands

**Backend**:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
# Create .env with Plaid credentials and DB connection
cp .env.example .env
# Edit .env with your Plaid sandbox client_id and secret
uvicorn main:app --reload --port 8000
```

**Frontend**:
```bash
cd frontend
npm install
npm run dev  # starts Vite dev server on http://localhost:5173
```

**Database** (with Docker Compose):
```bash
docker-compose up postgres  # or docker-compose up for full stack
```
Schema is created/patched automatically on backend startup — no separate migration
step. See "Adding a Database Migration" below.

**Run Full Stack Locally**:
```bash
docker-compose up
# Backend: http://localhost:8000
# Frontend: http://localhost:5173
# API docs: http://localhost:8000/docs
```

**Run Tests**:
```bash
# Backend
cd backend
pytest tests/

# Frontend (if Vitest setup exists)
cd frontend
npm run test
```

**Periodic Sync** (manual trigger for testing):
```bash
cd backend
python -c "from sync_engine import full_sync; full_sync()"
# Or via HTTP (after login, use Bearer token; or optional X-API-Key if API_KEY is set):
# curl -X POST http://localhost:8000/api/plaid/sync -H "Authorization: Bearer $TOKEN"
```

## Critical Security & Secrets Practices

### Environment Variables (Non-Negotiable)
- **PLAID_CLIENT_ID**, **PLAID_SANDBOX_SECRET** / **PLAID_PROD_SECRET**, **PLAID_ENV**
- **ENCRYPTION_KEY**: Fernet key for Plaid tokens at rest; also derives session signing unless `AUTH_TOKEN_KEY` is set
- **DATABASE_URL**: `sqlite:///ledger.db` for manual dev; PostgreSQL for Docker prod

### Optional
- **API_KEY**: legacy `X-API-Key` header for curl/automation — leave unset for browser-only use
- **AUTH_TOKEN_KEY**: independent session signing key (rotate `ENCRYPTION_KEY` without logout)
- **SESSION_TTL_DAYS**: session lifetime (default 30)
- **ALERT_WEBHOOK_URL**, **RESEND_API_KEY**, **PROPOSAL_SERVICE_KEY** — see README.md

### `.env` location
- **Manual dev** (`uvicorn` from `backend/`): `backend/.env`
- **Docker Compose**: root `.env` (see `.env.example`)
- **Frontend**: no secrets required (`frontend/.env.example` is empty by design)

### Token Storage
- Plaid access tokens are encrypted with Fernet before storing in the DB
- Decryption happens only in `plaid_service.py` when making API calls
- Access tokens **never appear in logs or API responses to frontend**

### Plaid API Environment
- Start with Plaid Sandbox for all development and testing
- Switch to Production only after:
  1. Plaid approves your account (requires submitting app details)
  2. You update `PLAID_ENV=production` in `.env`
  3. You generate new Production credentials and set `PLAID_CLIENT_ID` / `PLAID_PROD_SECRET`
- See `docs/PLAID_SETUP.md` for detailed Plaid app configuration (which products to enable: Transactions, Auth, Balance)

## Feature Overview (all phases shipped)

Core capabilities are documented in **docs/ARCHITECTURE.md** and **README.md**.
Summary:

- **Plaid**: Link, sync (`POST /api/plaid/sync`), update mode, delete item
- **Transactions**: search/filter, recategorize, bulk-categorize, hide, split, CSV import/export
- **Analytics**: overview KPIs, net worth, trends, cash-flow (Spending page)
- **Budgets**: full CRUD, suggest, onboarding; separate `budgets.db`
- **Investments**: holdings, history, refresh (`#investments` tab)
- **Subscriptions**: recurring charge detection
- **Alerts**: in-app (AlertsPanel + Settings); optional `ALERT_WEBHOOK_URL`
- **Weekly email**: optional Resend transport
- **AI Advisor**: MCP proposals (`PROPOSAL_SERVICE_KEY`) + Apply/Dismiss UI
- **Auth**: username/password on first run; Bearer session tokens

Dark-first UI (liquid-glass theme); no light-mode toggle planned.

## Important Plaid-Specific Decisions

### Transaction Sync Strategy
- Use Plaid's `/transactions/sync` endpoint (cursor-based, more efficient than deprecated `/transactions/get`)
- Store the sync cursor per Item in the DB to enable incremental syncs
- Handle pending vs. posted transactions; show pending separately if needed
- Transactions updated/removed by Plaid are handled via sync response's `removed` array

### Category Taxonomy
- Start with Plaid's PFC (Personal Finance Category) taxonomy as the default
- Allow users to create custom categories that override PFC
- Store both the Plaid category (for reference) and the user's override category in the Transaction model

### Access Token Encryption
- Use Fernet (symmetric, AES-128 in CBC mode) from the `cryptography` library
- Key is stored in `ENCRYPTION_KEY` env var; rotate it by re-encrypting all tokens if compromised
- Decryption happens only when calling Plaid APIs (in `plaid_service.py`)

### Known Plaid Limitations
- Historical account balances are NOT provided by Plaid (only current balance)
  - **Workaround**: snapshot account balances daily via scheduled job and query the snapshots for net-worth charts
- Robinhood Gold Card support depends on whether Robinhood is a linkable institution in your Plaid plan
  - **Check**: review Plaid's institution search tool or contact support to confirm coverage
- Some institutions have account ownership limits (you can't see someone else's account) — Plaid enforces this at link time

## Testing Strategy

### Backend
- Unit tests for `categorization.py` (rules engine logic, edge cases like overlapping rules)
- Unit tests for `sync_engine.py` (cursor management, transaction deduplication)
- Integration tests for `plaid_service.py` using Plaid's Sandbox credentials (test account linking, transaction fetch)
- Mock tests for sensitive operations (e.g., encryption/decryption without storing real tokens)

### Frontend
- Component tests for Dashboard, TransactionsList, PlaidLink (Vitest + React Testing Library if time allows)
- Manual testing of Plaid Link flow and categorization UI

### Manual Testing Checklist
1. Link a Plaid Sandbox account (use provided test credentials)
2. Sync transactions; verify they appear with Plaid categories
3. Create a category rule and verify it applies on next sync
4. Manually recategorize a transaction; verify it's not overwritten on next sync
5. Set a budget and overspend a category; verify alert/progress bar
6. Export transactions as CSV and open in spreadsheet; verify data integrity

## Extending the Project

### Adding a New Dashboard View
1. Create a new page in `/frontend/src/pages/MyDashboard.tsx`
2. Add a new data aggregation endpoint in `/backend/routes/analytics.py` (e.g., `GET /analytics/my-metric`)
3. Test the endpoint in isolation
4. Add the frontend component that calls the endpoint
5. Add a route and navigation link

### Adding a New Categorization Feature
1. Extend the `Transaction` model if needed (e.g., add a `split_allocations` JSON field for splits)
2. Add logic to `categorization.py` to handle the new feature
3. Write tests for the logic
4. Expose via a new endpoint in `/backend/routes/transactions.py`
5. Build the UI component in the frontend

### Deploying to Production
See `docs/PRODUCTION_CHECKLIST.md` for the full runbook. Short version for a
self-hosted deployment:
1. `docker-compose.prod.yml` is a self-contained stack (Postgres + backend +
   Caddy) — no bind mounts, no `--reload`, Caddy handles HTTPS and serves the
   built frontend while reverse-proxying `/api`, `/docs`, `/health`
2. Set `ENCRYPTION_KEY` and `POSTGRES_PASSWORD` in `.env` before first boot
3. `PlaidService.validate_config()` refuses to start if `PLAID_ENV=production`
   is set without production Plaid credentials
4. `CORS_ORIGINS` only needed if frontend and API are on different origins
   (usually unnecessary behind Caddy same-origin deploy)
5. Review `SECURITY.md` — session login + VPN/Tailscale for remote access

## Documentation Files

- **README.md**: User-facing setup, Plaid app setup, how to run, screenshots
- **docs/ARCHITECTURE.md**: Data flow diagram and component descriptions
- **docs/PLAID_SETUP.md**: Step-by-step Plaid app creation and credential configuration
- API endpoint reference: FastAPI's auto-generated `/docs` (no static docs/API.md file)
- **SECURITY.md**: Threat model, encryption practices, production hardening checklist
- **CONTRIBUTING.md**: Contribution guidelines (even though single-author for now)
- **.env.example**: Template environment variables with placeholder values

## Common Development Patterns

### Adding a Database Migration
There's no separate migration step or tool. Add the column to the relevant model in
`models.py`; `database.py::_ensure_columns()` additively patches existing SQLite DBs
with any new columns on the next backend startup (it never drops or alters existing
columns — new *tables* are handled by `create_all()` as usual).

### Running a Background Sync Manually
```bash
cd backend
python -m app.scheduler  # starts APScheduler
# Or: curl -X POST http://localhost:8000/api/plaid/sync -H "Authorization: Bearer $TOKEN"
```

### Debugging Plaid API Calls
- Enable request/response logging in `plaid_service.py` by setting `PLAID_DEBUG=true` in `.env`
- Use Plaid's API explorer at plaid.com/dashboard to test endpoints directly
- Check the transaction sync cursor is advancing in the DB (`items.plaid_sync_cursor`)

### Handling Plaid Link Errors
- Plaid Link returns error codes in `onExit` callback; log and display user-friendly messages
- Common issues: wrong environment (sandbox vs production), missing product enablement, institution not supported in chosen plan

## Known Issues & Workarounds

- **SQLite in production**: SQLite is fine for local dev but not suitable for production. Switch to PostgreSQL via Docker Compose or managed service.
- **Cross-origin requests**: If frontend and backend are on different ports locally, CORS is handled by FastAPI's `CORSMiddleware` — no changes needed.
- **Transaction timestamp precision**: Plaid returns dates, not datetimes. Store as date columns; if you need sub-day precision, track transaction post/pending times separately.

## Code Style & Conventions

- **Python**: Follow PEP 8. Use type hints for all functions. Format with `black` (configured in `pyproject.toml`).
- **TypeScript/React**: Use ESLint + Prettier. Components are functional with hooks; no class components.
- **Database**: Use SQLAlchemy ORM throughout; no raw SQL queries except in migrations.
- **Secrets**: Never hardcode sensitive values; always use env vars or `.env` file.
- **Comments**: Only document the "why" for non-obvious logic. Don't over-comment.

## Git Workflow

- Main branch (`main`) is production-ready. All changes via pull requests with clear commit messages.
- Branch naming: `feature/add-budget-alerts`, `fix/sync-cursor-bug`, etc.
- Commit messages: "Add budget alerting" or "Fix transaction deduplication in sync" — clear, past-tense.
- `.gitignore` includes: `.env`, `*.pyc`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`

## Current Implementation Status (2026-07-06)

All four original phases are complete. See **CHANGES.md** for recent work.

### Critical invariants (don't reintroduce)
1. `Transaction.date` must be a Python `date` object — convert with `date.fromisoformat()` in `plaid_service.py`
2. Plaid `account_id` is a string; `Transaction.account_id` is an integer FK — build `plaid_to_internal` mapping before insert
3. `strftime("%-d")` fails on Windows — use `str(date.day)` instead
4. `Item.last_sync_cursor` is the correct field name (not `plaid_sync_cursor`)
5. `PLAID_SANDBOX_SECRET` / `PLAID_PROD_SECRET` — selected by `PLAID_ENV`

### Net worth chart
- `GET /api/analytics/net-worth` appends today's live balance sum as the final point
- `POST /api/plaid/sync` refreshes balances and inserts today's `BalanceSnapshot` if missing

### Investments
- `#investments` tab; `sync_investments()` after each bank sync (isolated try/except)
- `POST /api/investments/refresh` for manual Plaid refresh + resync
- Requires Investments product in Plaid Dashboard — see `docs/PLAID_SETUP.md`

### Trends API
- `/api/analytics/trends` returns per-month spending/income, all category series,
  complete-month averages, `is_partial` flag for in-progress month

### Alerts & notifications
- In-app alerts via `app/alerts.py` + Settings toggles
- Webhook: `ALERT_WEBHOOK_URL` + `app/notifications.py` after sync
- Weekly email: `RESEND_API_KEY` + `WEEKLY_EMAIL_*` env vars

### Remaining candidates
- Multi-user auth, Alembic (if schema outgrows `_ensure_columns()`), frontend test suite

---

**Last Updated**: 2026-07-06
