# Ledger — Your Personal Finance Dashboard

Ledger is a private, self-hosted app that connects to your bank accounts and credit cards, automatically pulls in your transactions, and turns them into clean dashboards for spending, budgets, investments, and net worth. Everything runs **on your own computer** — your bank data never lives on someone else's server.

---

## Get started

### 1. Download the app

Grab the installer for your platform from **[Releases](https://github.com/OliverF21/Ledger/releases/latest)** — no Python, Node, or terminal required.

- **macOS**: download the `.dmg`, drag Ledger into Applications
- **Windows**: download the `.exe` or `.msi` installer and run it

The app is unsigned (no Apple/Microsoft developer certificate), so the OS will warn on first open:

- **Windows:** SmartScreen shows "Windows protected your PC" — click **More info → Run anyway**.
- **macOS:** open it once via **System Settings → Privacy & Security → "Open Anyway"**. If instead you see **"Ledger" is damaged and can't be opened**, that's a misleading Gatekeeper message for unsigned, browser-downloaded apps — it isn't actually corrupted. Fix it with:
  ```bash
  xattr -cr /Applications/Ledger.app
  ```

More detail (first-launch timing, auto-updates, lost-password recovery): **[desktop/README.md](desktop/README.md)**.

### 2. Get a free Plaid API key

Plaid is the trusted middleman that connects Ledger to your bank — it's how Ledger reads your transactions without ever seeing your bank password. Ledger needs your own Plaid API key (free):

1. Create a free account at **[dashboard.plaid.com](https://dashboard.plaid.com/)**.
2. Go to **Team Settings → Keys** and copy your **client_id** and **Sandbox secret**.
3. Keep that tab open — you'll paste both into Ledger in the next step.

Start in **Sandbox** mode (fake test banks, no real accounts) — you can switch to your real bank later from **Settings → Plaid** once you're ready (see [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md) "Moving to Production").

### 3. First launch

1. Open Ledger and **create your account** (username + password — this is your own local login, no email, no cloud).
2. Paste your **client_id** and **Sandbox secret** from Step 2 into the setup wizard.
3. Optionally set a **recovery email** so you can reset your password by email later if you forget it (needs your own free [Resend](https://resend.com/api-keys) key — see the wizard, or **Settings → Recovery email** anytime).
4. **Link a bank**: in Sandbox mode, pick any test institution and log in with `user_good` / `pass_good` ([full sandbox credentials](https://plaid.com/docs/sandbox/test-credentials/)).
5. Click **Sync now**, then explore the **Overview**, **Transactions**, **Budgets**, **Trends**, and **Investments** tabs.

That's it — you're running Ledger. 🎉

---

## What Ledger can do

| Area              | What you get                                                                                                           |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------|
| **Accounts**      | Securely link banks and credit cards; multiple institutions; sync on demand or automatically every few hours          |
| **Transactions**  | Search, filter, recategorize, split shared expenses, hide rows, export to a spreadsheet (CSV)                         |
| **Cash flow**     | Monthly income vs. spending, category breakdowns, flow diagrams                                                       |
| **Budgets**       | Monthly limits per category with progress bars and overage alerts                                                     |
| **Trends**        | 3 / 6 / 12 / 24-month spending patterns                                                                               |
| **Investments**   | Brokerage holdings and performance (needs the Plaid Investments product)                                              |
| **Subscriptions** | Automatic detection of recurring charges                                                                              |
| **Net worth**     | Daily balance snapshots that build a net-worth-over-time chart                                                        |
| **Crypto wallets**| Optional read-only Robinhood Chain addresses (USDG + majors) folded into net worth                                    |
| **Alerts**        | In-app notifications, plus optional push to Slack / Discord / your phone                                              |
| **Weekly email**  | Optional spending-vs-budget summary in your inbox                                                                     |
| **AI Advisor**    | Claude (Anthropic's AI) can look at your finances and *suggest* budget changes — you approve or reject them in the app |

---

## Optional extras

None of these are required. Set them up from **Settings** only if you want the feature.

- **Crypto wallets** — in the desktop app, paste an Alchemy API key and a public `0x` address under **Settings → Crypto wallets** (Robinhood Chain USDG + curated majors fold into net worth). For source installs you can also set `ALCHEMY_API_KEY` in `backend/.env`.
- **Alerts to your phone or chat** — add a webhook URL for budget-overage and large-transaction alerts pushed to Slack, Discord, or [ntfy](https://ntfy.sh/).
- **Weekly summary email** — a free [Resend](https://resend.com/) key enables a spending-vs-budget email on a schedule you set.
- **AI Advisor (Claude)** — a local MCP server lets [Claude Desktop](https://claude.ai/download) read your finances and *propose* budget changes; you always Apply or Dismiss them yourself. Setup + example prompts: **[backend/MCP_SETUP.md](backend/MCP_SETUP.md)**.
- **Import from another app** — bring in transaction history via CSV; see **[docs/PLAID_SETUP.md](docs/PLAID_SETUP.md)** and the setup wizard's "Import your data" link.
- **Real bank accounts** — once you've tried Sandbox, see **[docs/PLAID_SETUP.md](docs/PLAID_SETUP.md)** "Moving to Production" to request Plaid production access and switch over.

---

## Running from source instead

Prefer to build it yourself, self-host on a server, or contribute code? Prerequisites: Python 3.11+, Node.js 18+, Git.

```bash
git clone https://github.com/OliverF21/ledger.git && cd ledger

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env   # fill in PLAID_CLIENT_ID, PLAID_SANDBOX_SECRET, and a generated ENCRYPTION_KEY
cd ..

# Frontend
cd frontend && npm install && npm run build && cd ..

# Run
cd backend && source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000
```

Generate `ENCRYPTION_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — **never change it after linking a bank account**, it's the only thing that unlocks your saved connection.

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** and continue from "First launch" above.

**Updating:** `git pull`, then re-run the `pip install` and `npm install && npm run build` steps.

**Always-on without a terminal window:** on Windows, `scripts/install_ledger_service.ps1` registers Ledger as a service that starts at boot and restarts on crash — the recommended path if you also use the AI Advisor on a self-hosted box. For live frontend editing, run `uvicorn main:app --reload` and `npm run dev` in separate terminals and use `http://localhost:5173`.

**Your data lives in** `backend/ledger.db` (transactions, accounts) and `backend/budgets.db` (budgets) — back these up by copying the files while the app is stopped.

### Settings reference (source / self-hosted only)

Desktop-app users configure everything from **Settings** in the app. Source/self-hosted installs configure `backend/.env` instead (see `backend/.env.example` for the full annotated list):

| Setting                | What it is                                                        |
| ----------------------- | ----------------------------------------------------------------- |
| `PLAID_CLIENT_ID`      | Your Plaid client ID                                              |
| `PLAID_SANDBOX_SECRET` | Plaid Sandbox secret (used when `PLAID_ENV=sandbox`)              |
| `PLAID_PROD_SECRET`    | Plaid Production secret (used when `PLAID_ENV=production`)        |
| `PLAID_ENV`            | `sandbox` (test banks) or `production` (real banks)               |
| `ENCRYPTION_KEY`       | Scrambles saved bank connections — **never change after linking** |
| `ALCHEMY_API_KEY`      | Optional fallback for Robinhood Chain wallets (desktop: Settings) |
| `SYNC_INTERVAL_HOURS`  | How often to auto-sync (default 6)                                   |
| `RESEND_API_KEY`       | Enables the weekly summary email                                     |
| `RESET_EMERGENCY_RESEND_API_KEY` | Enables email-based password reset                         |
| `PROPOSAL_SERVICE_KEY` | Enables the AI Advisor's budget proposals                            |
| `ALERT_WEBHOOK_URL`    | Push alerts to Slack/Discord/ntfy                                    |
| `CORS_ORIGINS`         | Only needed if the app and engine run on different addresses         |

### Troubleshooting (source installs)

| Symptom                                                 | Fix                                                                                                                                                                                                                |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `command not found: python3` / `node` / `git`            | The tool isn't installed, or the terminal wasn't reopened after installing. On Windows try `python` instead of `python3`.       |
| `No module named ...` when starting                      | Your `.venv` isn't active, or `pip install -r requirements.txt` hasn't run.                              |
| Page at `:8000` won't load / "connection refused"        | The engine isn't running — check that terminal is still open and shows "Uvicorn running."                                                                                     |
| "Port 8000 is already in use"                             | Start with a different port: `uvicorn main:app --port 8001`.                                          |
| **🪟 "running scripts is disabled on this system"**       | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then retry.                                                                                                                                        |
| Plaid pop-up shows an error                               | Double-check `PLAID_CLIENT_ID` / `PLAID_SANDBOX_SECRET`, that `PLAID_ENV=sandbox`, and that **Transactions** is enabled in the Plaid dashboard. See [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md). |
| A page of JSON instead of the app, or a blank page        | The frontend wasn't built: `cd frontend && npm install && npm run build`, then restart the engine.                                                                    |

Still stuck? **[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)** — if that loads, the engine is fine and the problem is the frontend build.

---

## Security: please read

Ledger holds sensitive financial data. Treat it like private infrastructure:

- **Don't put it on the public internet** without strong protection. For remote access, use a VPN like [Tailscale](https://tailscale.com/).
- Your bank connection tokens are **encrypted at rest** and never shown to the browser.
- Keep `backend/.env` and your `.db` files private. **Store `ENCRYPTION_KEY` somewhere separate from your database backups** — together, they unlock your bank connection.
- Back up `backend/ledger.db` and `backend/budgets.db` regularly (copy the files while the app is stopped, or use `sqlite3 backend/ledger.db ".backup 'ledger-backup.db'"`).

Full threat model and hardening checklist: **[SECURITY.md](SECURITY.md)**.

---

## More documentation

| Document                                                     | What's inside                                      |
| ------------------------------------------------------------ | -------------------------------------------------- |
| [desktop/README.md](desktop/README.md)                       | Desktop app details, auto-update, lost-password recovery |
| [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md)                   | Setting up Plaid and connecting real banks         |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)                 | How Ledger is built (for the curious / developers) |
| [backend/MCP_SETUP.md](backend/MCP_SETUP.md)                 | Connecting Claude Desktop (AI Advisor)             |
| [SECURITY.md](SECURITY.md)                                   | Security model and best practices                  |
| [CONTRIBUTING.md](CONTRIBUTING.md)                           | Contributing to the project                        |

When the engine is running, an interactive list of everything the backend can do is at **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## License

MIT — see [LICENSE](LICENSE).

**Ledger — your money, your machine, your control.**
