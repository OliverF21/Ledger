# Ledger Architecture

High-level architecture, data flow, and design decisions for the Ledger personal
finance dashboard.

**Last updated**: 2026-07-06

---

## System Overview

Ledger is a three-tier web application with an optional MCP sidecar for AI-assisted
budget proposals.

```
┌──────────────────────────────────────────────────────────────────┐
│ Frontend (React + TypeScript + Vite)                             │
│ - Hash-based SPA (#overview, #transactions, …)                   │
│ - Plaid Link (react-plaid-link)                                  │
│ - Session token in localStorage → Authorization: Bearer          │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP/REST (JSON)  /api/*
                             ↓
┌──────────────────────────────────────────────────────────────────┐
│ Backend (FastAPI + Python)                                       │
│ - Raw requests-based Plaid REST wrapper (plaid_service.py)       │
│ - Cursor-based transaction sync (sync_engine.py)                 │
│ - Categorization rules engine (categorization.py)                │
│ - APScheduler background jobs (scheduler.py)                     │
│ - Optional MCP server (mcp_server/) for Claude Desktop           │
└──────────────┬──────────────────────────────┬──────────────────────┘
               │ SQL                          │ SQL (read-only for MCP)
               ↓                              ↓
┌──────────────────────────────┐  ┌──────────────────────────────┐
│ ledger.db / PostgreSQL       │  │ budgets.db                   │
│ Items, Accounts, Transactions│  │ budgets, proposals           │
│ Investments, Users, …        │  │ (separate file to avoid locks)│
└──────────────────────────────┘  └──────────────────────────────┘
               ↕
        Plaid REST API (no official SDK)
```

### External services

| Service | Role |
|---------|------|
| **Plaid** | Bank linking, transaction sync, balances, investment holdings |
| **Resend** (optional) | Weekly spending summary email (`RESEND_API_KEY`) |
| **Webhook URL** (optional) | Budget/large-tx alerts (`ALERT_WEBHOOK_URL`) |

---

## Authentication

Ledger is single-user (hardcoded `user_id=1`).

1. **First run**: `GET /api/setup/status` — if no password is set, the UI shows
   registration (`POST /api/auth/register`).
2. **Login**: `POST /api/auth/login` returns a Fernet-signed session token.
3. **API calls**: `src/api/client.ts` attaches `Authorization: Bearer <token>`.
   Tokens expire after `SESSION_TTL_DAYS` (default 30).
4. **Optional automation**: set `API_KEY` in backend env; pass `X-API-Key` header.
   Leave unset to disable that path. No frontend build-time secret is required.

Session signing uses a key derived from `ENCRYPTION_KEY` unless `AUTH_TOKEN_KEY`
is set (allows rotating Plaid-token encryption without logging users out).

**MCP proposals** use a separate scoped key: `PROPOSAL_SERVICE_KEY` is accepted
only on `POST /api/proposals` (create-only; user must Apply/Dismiss in the UI).

---

## Data Flow: Connecting an Account

1. User opens **Settings → Connect account** (Plaid Link).
2. Frontend calls `POST /api/plaid/create_link_token`.
3. Backend calls Plaid `/link/token/create` (products: auth, transactions,
   investments) and returns `link_token`.
4. User completes Plaid Link; frontend receives `public_token`.
5. Frontend calls `POST /api/plaid/set_access_token` with `public_token`.
6. Backend exchanges for `access_token` + `item_id`, encrypts the token with
   Fernet, stores an `Item`, fetches accounts, and triggers an initial sync.

**Update mode**: Settings can request a link token with `access_token` set so the
user can re-authenticate or grant additional consent (e.g. investments).

---

## Data Flow: Syncing Transactions

Triggered by **Sync now** (`POST /api/plaid/sync`), the APScheduler interval
(default every 6 hours), or automatically after linking.

For each real `Item` (excludes `manual_import` and `test_item`):

1. Decrypt `access_token_encrypted`.
2. Paginate Plaid `/transactions/sync` using `Item.last_sync_cursor`.
3. Upsert new/modified transactions; mark `removed` rows from Plaid's `removed` list.
4. Run categorization rules (respecting `manual_override`).
5. Refresh account balances from Plaid; insert today's `BalanceSnapshot` if missing.
6. Backfill enrichment for legacy rows via `/transactions/get` when needed.
7. Call `sync_investments()` in a try/except (brokerage failure must not roll back
   bank transaction sync).
8. After all items, optionally fire `ALERT_WEBHOOK_URL` for new budget/large-tx alerts.

Per-page cursor commits make sync resumable if the process crashes mid-run.

---

## Data Flow: Categorization

### Default: Plaid Personal Finance Categories (PFC)

Synced transactions store `category_plaid`, `category_plaid_detailed`, and
enrichment JSON. Display/rollup logic prefers user overrides, then detailed PFC
parent, then primary PFC (`Transaction.rollup_category` in `models.py`).

### User overrides

| Mechanism | When applied | Persists across sync? |
|-----------|--------------|------------------------|
| **Category rules** | On sync + backfill on rule create | Yes, unless `manual_override` |
| **Manual recategorize** | `PUT /api/transactions/{id}/category` | Yes (`manual_override=True`) |
| **Bulk recategorize** | `POST /api/transactions/bulk-categorize` | Yes |

Rules are regex patterns with priority ordering; invalid regex falls back to
substring match.

---

## Investments

Separate from bank `transactions` — not included in spending analytics.

| Model | Purpose |
|-------|---------|
| `Security` | Ticker, name, type, close price (keyed by `plaid_security_id`) |
| `Holding` | Position per `(account_id, security_id)` |
| `InvestmentTransaction` | Buys, sells, dividends, fees |

API: `GET /api/investments/summary|holdings|transactions|history`,
`POST /api/investments/refresh` (Plaid refresh + resync).

UI: `#investments` tab between Budgets and Trends.

---

## AI Advisor (MCP)

```
Claude Desktop → MCP tools (read analytics, plan_goal / TVM, propose_budget)
            → POST /api/proposals  (PROPOSAL_SERVICE_KEY)
            → pending row in budgets.db
            → user reviews in Advisor UI → Apply or Dismiss
```

MCP reads SQLite directly for analytics; only proposal **creation** goes through
the API with the scoped service key. Goal planning (`planning_capacity`,
`plan_goal`, `plan_goal_from_expenses`) runs time-value-of-money math in
`app/services/tvm.py` — Claude calls those tools and does not invent NPER/PMT/FV.
See `docs/MCP_SETUP.md` and `docs/MCP_FINANCIAL_GOALS_PLAN.md`.

---

## Database Schema (summary)

### `ledger.db` (or PostgreSQL via `DATABASE_URL`)

| Table | Notes |
|-------|-------|
| `users` | Single row; scrypt password hash; alert prefs |
| `items` | Encrypted Plaid tokens, sync cursor, institution metadata |
| `accounts` | Linked accounts and current balances |
| `transactions` | Spending data; PFC + user category; splits; hidden flag |
| `categories`, `category_rules` | User taxonomy and merchant rules |
| `balance_snapshots` | Daily balance history for net-worth chart |
| `securities`, `holdings`, `investment_transactions` | Brokerage data |

### `budgets.db` (via `BUDGETS_DATABASE_URL`, default `budgets.db`)

| Table | Notes |
|-------|-------|
| `budgets` | Monthly limits per category (no FK to ledger — joined in Python) |
| `proposals` | Pending/applied/dismissed AI advisor suggestions |

### Migrations

No Alembic. On startup:

- `create_all()` for new tables.
- `_ensure_columns()` in `database.py` additively patches **SQLite only**.
  PostgreSQL column adds require manual SQL or recreation.

---

## API Endpoints (summary)

All routes below are under `/api` unless noted. Interactive OpenAPI docs:
`http://localhost:8000/docs`.

**Unauthenticated**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/setup/status` | First-run check |
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Issue session token |

**Authenticated** (`Bearer` or optional `X-API-Key`)

| Prefix | Key endpoints |
|--------|---------------|
| `/plaid` | `create_link_token`, `set_access_token`, `accounts`, `sync`, `sync/status`, `DELETE item/{id}` |
| `/transactions` | list, `/{id}/category`, `bulk-categorize`, `toggle-hide`, `split`, `import` (CSV) |
| `/analytics` | `summary`, `net-worth`, `trends`, `cash-flow` |
| `/budgets` | CRUD, `suggest` |
| `/categorization-rules` | CRUD, reorder |
| `/settings` | alert prefs, active alerts, weekly-email prefs |
| `/subscriptions` | recurring charge detection |
| `/investments` | summary, holdings, transactions, history, refresh |
| `/weekly-email` | preview, send |
| `/proposals` | list, apply, dismiss, undo (create = service key only) |

Public (no auth): `GET /`, `GET /health`.

When `frontend/dist` exists, FastAPI also serves the SPA on port 8000 (same-origin
deployment — no CORS or frontend secrets needed).

---

## Background Jobs (APScheduler)

| Job | Schedule | Action |
|-----|----------|--------|
| Sync all Plaid items | Every `SYNC_INTERVAL_HOURS` (default 6) | `sync_item()` + webhook alerts |
| Weekly summary email | Cron (default Mon 08:00) | `send_weekly_summary()` if Resend configured |
| Expire stale proposals | Daily 03:00 | Mark pending proposals older than `PROPOSAL_TTL_DAYS` expired |

Balance snapshots are taken during sync, not by a separate nightly job.

---

## Key Design Decisions

1. **Single-user** — `user_id=1` everywhere; schema ready for future multi-user.
2. **Encrypted Plaid tokens** — Fernet at rest; decrypt only in `plaid_service.py`.
3. **Cursor-based sync** — Plaid `/transactions/sync` with per-page commits.
4. **Separate budgets DB** — avoids SQLite write-lock contention with transaction sync.
5. **No money movement** — read-only Plaid permissions; monitoring only.
6. **Raw Plaid HTTP** — no `plaid-python` SDK dependency.
7. **Dark-first UI** — liquid-glass theme; no light-mode toggle planned.

---

## Deployment Modes

| Mode | How | Database | Notes |
|------|-----|----------|-------|
| **Desktop app** | native Tauri app, `desktop/` | SQLite | Bundled backend via PyInstaller; recommended for most users |
| **Single-port** | `npm run build` + `uvicorn` on :8000 | SQLite | Same-origin SPA; always-on home server |
| **Dev** | Vite :5173 + backend :8000 | SQLite | Vite proxies `/api` |

---

## Testing

Backend tests live in `backend/tests/` (auth, proposals, Plaid live-data helpers,
category labels, MCP spending). Run:

```bash
cd backend && pytest tests/
```

Frontend Vitest is configured but has no test files yet.

---

## Further Reading

- **README.md** — setup and user-facing features
- **CLAUDE.md** — developer conventions and current status
- **SECURITY.md** — threat model and hardening
- **CHANGES.md** — recent feature changelog
