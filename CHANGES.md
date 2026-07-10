# CHANGES — 2026-07-03 Audit & Remaining-Phase Implementation

This document records every change made in the 2026-07-03 session: what was
done, why, and **exactly how to reverse it**. Each change is its own git
commit, so reversal is always possible with a single `git revert` unless
noted otherwise. It also records the audit findings that were intentionally
**not** implemented, with recommendations.

Branch: `feature/investments-portfolio`.

---

## Part 1 — Changes made

### 1. Stop tracking SQLite WAL/SHM sidecar files — `8d37482` (security, critical)

**What**: Removed `backend/budgets.db-shm`, `backend/budgets.db-wal`,
`backend/ledger_clean.db-shm`, `backend/ledger_clean.db-wal` from git
tracking (files remain on disk) and extended `.gitignore` with `*.db-wal`,
`*.db-shm`, `*.db-journal`, `*.sqlite-wal`, `*.sqlite-shm`, `*.log`.

**Why**: `.gitignore` covered `*.db` but not the WAL/SHM sidecars SQLite
creates in WAL mode. WAL files contain recent database pages — i.e. **your
real transactions, balances, and merchant history** — and four of them were
committed. Publishing this repo would have published your financial data.

**⚠️ Residual risk**: the blobs still exist in **git history** (commits
before `8d37482`). Before making the repo public you must either scrub
history (`git filter-repo --invert-paths --path-glob '*.db-wal' --path-glob
'*.db-shm'`) or squash everything into a fresh initial commit. Reverting
this commit does not remove that obligation.

**How to reverse**: `git revert 8d37482` — but don't: that re-tracks live
financial data. If you only want to un-ignore logs, delete the `*.log` line
from `.gitignore`.

---

### 2. Checkpoint commit of pre-existing work — `9686e58` (housekeeping)

**What**: Committed, unmodified, all work that previous sessions had left
uncommitted in the working tree (liquid-glass UI theme, `app/services/`
extraction, MCP server, prod Docker stack, tests, doc updates).

**Why**: The session's new changes needed to land as clean, individually
revertible commits. Mixing them with ~3,500 lines of pre-existing
uncommitted work would have made selective rollback impossible.

**Note**: `frontend/liquid glass/` (design-handoff assets) was intentionally
left untracked — decide separately whether design sources belong in the
repo (see Part 2, item R7).

**How to reverse**: `git revert 9686e58` restores the tree to the
pre-checkpoint state **but** also reverts the prior sessions' features (MCP
server, prod stack, glass UI). To reverse only a specific file, use
`git checkout 8d37482 -- <path>`.

---

### 3. Trends overhaul — `faf4a3d` (the centerpiece)

**What — backend** (`/api/analytics/trends`, response reshaped;
`build_trends()` added to `backend/app/services/analytics_service.py`):
- Per-month totals: spending, income, net — not just category lines.
- **All** categories returned (was: top 5 only), each with a per-month
  series, window total, complete-month average, share of spending, and
  last-complete-month vs prior-average change.
- The in-progress current month is flagged `is_partial` and **excluded from
  every average and comparison**. Previously it was averaged in, so every
  trend appeared to crash at the end of the window.
- Months before the first transaction ever recorded are treated as
  *no data*, not `$0` — young accounts no longer show phantom
  “spending doubled” artifacts.
- A prior same-length window is aggregated in the same query to power the
  headline “avg monthly spend vs prior period” comparison.
- Removed dead helpers in `routes/analytics.py` left over from the
  service-layer extraction (they referenced an import that no longer
  exists; they were unreachable but would confuse future readers).

**What — frontend** (`frontend/src/pages/Trends.tsx` rebuilt):
- KPI row: average monthly spend (with change badge vs the prior period,
  red = spending up), period total (noting “includes <month> so far”), and
  period income.
- Insight chips: the biggest category movers vs their own typical month
  (categories averaging under $25/mo are filtered out — a $4→$9 jump is not
  a story). Clicking a chip isolates that category.
- Main chart: monthly spending bars + income line on a single dollar axis.
  The partial month is drawn lighter, with a footnote explaining why.
- Category breakdown table: every category with color key, sparkline
  (complete months only), total, avg/month, vs-typical badge, and share
  bar. Clicking a row isolates that category in the main chart.
- Range control: 3/6/12/24 months (was 6/12).
- `App.tsx`: the Trends header no longer hardcodes “Last 6 months”.

**Why**: The old page was one top-5 spaghetti line chart plus three cards
that said “sparklines” but contained no sparklines. It had two outright
correctness problems (partial-month skew; no-data months counted as $0)
that made the trends actively misleading, which is why it “needed
significant improvement to be usable”.

**How to reverse**: `git revert faf4a3d` (restores the old endpoint shape
and old page together — they must move together, the response schema
changed).

---

### 4. Amount-range filter on Transactions — `d4c9c13` (Phase 3 completion)

**What**: Min/Max dollar inputs in the Transactions filter bar, matching on
absolute amount so refunds and charges filter alike; footer “filtered from
N” now accounts for account and amount filters too.

**Why**: The Phase 3 spec called for search/filter by
merchant/category/account/**amount range**; amount range was the one piece
missing.

**How to reverse**: `git revert d4c9c13`.

---

### 5. Webhook alert notifications — `11e9e10` (Phase 4 completion)

**What**: If `ALERT_WEBHOOK_URL` is set, the 6-hourly background sync
delivers **new** budget-overage and large-transaction alerts as a JSON POST
`{"text": ..., "content": ...}` (Slack- and Discord-compatible; ntfy and
generic receivers work too).
- `backend/app/alerts.py`: alert computation extracted from
  `routes/settings.py` so the in-app panel and the webhook can never
  disagree about what counts as an alert.
- `backend/app/notifications.py`: delivery + once-per-alert dedupe
  (budgets: once per category per month; large transactions: once per
  transaction). Dedupe state lives in a new `users.alerts_webhook_state`
  column (JSON list, pruned to currently-active alerts so it cannot grow
  unboundedly). State advances only after a successful POST, so failed
  deliveries retry on the next cycle. The URL is never logged — webhook
  URLs embed secret tokens.
- `scheduler.py` calls the notifier after each sync cycle inside its own
  try/except, so alerting can never break syncing.
- Documented in both `.env.example` files; passed through in
  `docker-compose.prod.yml`.

**Why**: Phase 4 promised “email/webhook alerting”. Alerts existed only as
an in-app panel — you had to open the dashboard to find out you had blown a
budget. A webhook is the self-hosting-friendly transport: no SMTP
credentials, works with Slack/Discord/ntfy/Home Assistant. Email was
deliberately skipped (see R4).

**Verified**: against a local HTTP listener — one batched POST for new
alerts, zero on re-run (dedupe), failed-delivery retry path, DB state
restored after the test.

**How to reverse**: `git revert 11e9e10`. The `alerts_webhook_state` column
will remain in existing SQLite files (`_ensure_columns()` is additive-only);
it is harmless, but can be dropped with
`ALTER TABLE users DROP COLUMN alerts_webhook_state;` (SQLite ≥ 3.35).

---

### 6. Parameterize dev Postgres password — `277559d` (open-sourcing prep)

**What**: `docker-compose.yml` now uses
`POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ledger_password}` (and the
backend’s `DATABASE_URL` interpolates the same variable) instead of a
hardcoded literal; also forwards `ALERT_WEBHOOK_URL` like the prod stack.

**Why**: Last hardcoded credential in tracked files. The default keeps
`docker-compose up` working with zero configuration for local dev, while
letting anyone override without editing a tracked file.

**How to reverse**: `git revert 277559d`.

---

### 7. Documentation truth-up — (this commit)

**What**: README roadmap now reflects reality (Phases 1–4 complete;
subscription detection, alerts, and webhook alerting checked off; “dark
mode with theme toggle” corrected to “dark-first UI” — no toggle exists);
`ALERT_WEBHOOK_URL` documented in the README config list; CLAUDE.md’s
stale “Next Up (Phase 3)” section replaced with current status; this
CHANGES.md added.

**Why**: The docs described a project two phases behind the code. For
open-sourcing, a README that promises a theme toggle that doesn’t exist is
worse than no claim at all.

**How to reverse**: `git revert <this commit>`.

---

## Part 2 — Audit findings **not** implemented (recommendations)

**R1 — Scrub git history before open-sourcing (critical).** Beyond the WAL
blobs (change 1), history predating the security pass may contain other
sensitive material. Recommended: squash to a fresh initial commit when
publishing (simplest and provably clean), or run `git filter-repo`.
Also rotate `API_KEY`/`ENCRYPTION_KEY` if history is ever published as-is.

**R2 — Chart palette fails accessibility validation.** The shared
`CATEGORY_COLORS` palette was run through a formal palette validator
against the dark surface: adjacent-pair colorblind separation passes (ΔE
12.3, floor band), but several colors sit outside the ideal lightness band
and `#565c69` (slot 10) reads as gray and falls below 3:1 contrast. The new
Trends page compensates (every category is direct-labeled in the table;
the main chart distinguishes series by form, bar vs line, not color) — but
a lightness-tuned palette rework across Overview/Spending/Budgets/Trends
would fix it at the root. Cross-app visual change; needs a design pass, not
a patch.

**R3 — Single shared API key is the auth ceiling.** Fine for one user on a
private network; not fine on the public internet (no rate limiting, no
sessions, no revocation granularity). If public exposure is ever wanted:
put it behind an authenticating reverse proxy (Authelia/Cloudflare Access)
or build session auth. `SECURITY.md` already says this; it remains true.

**R4 — Email alerting intentionally skipped.** SMTP configuration is the
single biggest support burden in self-hosted apps (credentials, ports,
spam filtering). Webhooks reach email anyway via Zapier/ntfy relays. If
email is ever really wanted, add an SMTP transport beside
`notifications.py`'s webhook transport.

**R5 — Light theme intentionally skipped.** The Phase 4 “dark mode toggle”
item predates the liquid-glass redesign, which is dark-first by
construction (aurora background, white-alpha glass surfaces). A light theme
is a full design project, not a toggle. README updated to say so.

**R6 — Vitest scaffold has zero tests.** `vitest` + Testing Library are
installed but no frontend test files exist. Either add a few smoke tests
(Trends table rendering would be a good first target) or drop the dev
dependencies.

**R7 — `frontend/liquid glass/` is untracked.** Design-handoff assets sit
in the working tree but not in git. Decide: commit them (if they should
ship with the repo) or move them out. Left untracked to avoid bloating the
repo without a decision.

**R8 — `backend/ledger_clean.db*` and `cleanup_db.ps1` look like finished
one-offs.** If the DB-cleanup migration is done, delete the leftover files
(they're gitignored now, so this is disk hygiene, not repo hygiene).

**R9 — Trends colors are assigned by rank, not identity.** Switching the
range can re-rank categories and therefore recolor them (same behavior as
the rest of the app). A stable name→color assignment table would fix this
app-wide; do it together with R2.

---

## Part 3 — How to verify (all done this session)

- `cd backend && python -m pytest tests/` → 7 passed
- Backend boots: `python -c "import main"` with `.env` loaded → OK
- `GET /api/analytics/trends?months=6` over HTTP with `X-API-Key` → new
  shape, correct partial-month flag, sensible averages against live data
- Webhook: local listener received one batched POST; dedupe verified
- `cd frontend && npm run build` → `tsc` clean, Vite build succeeds
