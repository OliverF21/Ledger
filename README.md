# Ledger

A personal finance app that runs on your computer. It links your bank accounts through Plaid, pulls in transactions, and shows spending, budgets, investments, and net worth. Your data stays on your machine.

---

## Get started

### 1. Download the app

Installers are on the **[Releases](https://github.com/OliverF21/Ledger/releases/latest)** page. You don't need Python or Node for the desktop build.

- **macOS:** download the `.dmg` and drag Ledger into Applications
- **Windows:** download the `.exe` or `.msi` and run it

The app isn't code-signed, so the OS will complain the first time:

- **Windows:** SmartScreen says "Windows protected your PC." Click **More info**, then **Run anyway**.
- **macOS:** allow it under **System Settings → Privacy & Security → Open Anyway**. If you get **"Ledger" is damaged and can't be opened**, that's Gatekeeper being weird about unsigned downloads from a browser, not a broken file. Fix it with:
  ```bash
  xattr -cr /Applications/Ledger.app
  ```

More on first launch, auto-updates, and password recovery: **[desktop/README.md](desktop/README.md)**.

### 2. Get a Plaid API key

Ledger talks to your bank through [Plaid](https://plaid.com/). You need your own free API keys:

1. Sign up at **[dashboard.plaid.com](https://dashboard.plaid.com/)**.
2. Under **Team Settings → Keys**, copy the **client_id** and **Sandbox secret**.
3. Leave that tab open so you can paste them into Ledger next.

Start in **Sandbox** (fake banks, no real money). When you're ready for a real account, switch under **Settings → Plaid**. Details in [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md) under "Moving to Production".

### 3. First launch

1. Open Ledger and create a local username/password. There's no cloud account.
2. Paste the **client_id** and **Sandbox secret** into the setup wizard.
3. Optional: add a **recovery email** if you want password reset by email. That needs a free [Resend](https://resend.com/api-keys) key (wizard, or **Settings → Recovery email** later).
4. Link a bank. In Sandbox, any test institution works with `user_good` / `pass_good` ([sandbox credentials](https://plaid.com/docs/sandbox/test-credentials/)).
5. Hit **Sync now**, then poke around Overview, Transactions, Budgets, Trends, and Investments.

---

## Features

| Area | Notes |
| --- | --- |
| **Accounts** | Link banks and cards from multiple institutions. Sync manually or on a schedule. |
| **Transactions** | Search, filter, recategorize, split expenses, hide rows, export CSV. |
| **Cash flow** | Monthly income vs spending, by category. |
| **Budgets** | Per-category monthly limits, progress, overage alerts. Limits carry into new months. |
| **Trends** | Spending over 3 / 6 / 12 / 24 months. |
| **Investments** | Brokerage holdings and performance (needs Plaid Investments). |
| **Subscriptions** | Detects recurring charges. |
| **Net worth** | Daily balance snapshots over time. |
| **Crypto wallets** | Optional Robinhood Chain addresses (USDG, majors, Earn/steakUSDG) in net worth. |
| **Alerts** | In-app, or push to Slack / Discord / [ntfy](https://ntfy.sh/). |
| **Weekly email** | Spending vs budget summary (needs Resend). |
| **AI Advisor** | Claude can suggest budget changes. You still Apply or Dismiss each one yourself. |

### Optional setup

Skip anything you don't care about. All of this is under **Settings** (or `backend/.env` if you're running from source).

- **Crypto wallets:** Alchemy API key + a public `0x` address under **Settings → Crypto wallets**. Source installs can use `ALCHEMY_API_KEY` in `.env` instead.
- **Webhook alerts:** set a URL for budget overages and large transactions (Slack, Discord, or ntfy).
- **Weekly email:** Resend API key + schedule.
- **AI Advisor:** local MCP server for [Claude Desktop](https://claude.ai/download). See **[backend/MCP_SETUP.md](backend/MCP_SETUP.md)**.
- **CSV import:** bring history from another app. Wizard has an "Import your data" link; also [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md).
- **Real banks:** after Sandbox, follow "Moving to Production" in [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md).

---

## Running from source

Useful if you want to self-host, hack on the code, or skip the desktop wrapper. Needs Python 3.11+, Node 18+, and Git.

```bash
git clone https://github.com/OliverF21/ledger.git && cd ledger

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env   # fill in PLAID_CLIENT_ID, PLAID_SANDBOX_SECRET, ENCRYPTION_KEY
cd ..

# Frontend
cd frontend && npm install && npm run build && cd ..

# Run
cd backend && source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000
```

Generate `ENCRYPTION_KEY` with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Don't change that key after you've linked a bank. It's what decrypts the stored connection tokens.

Then open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** and follow the first-launch steps above.

**Updating:** `git pull`, then re-run `pip install -r requirements.txt` and `npm install && npm run build`.

**Windows service:** `scripts/install_ledger_service.ps1` installs Ledger as a boot-time service that restarts on crash. Handy if you run the AI Advisor on a box that should stay up. For frontend hot reload, run `uvicorn main:app --reload` and `npm run dev` separately and use `http://localhost:5173`.

**Data files:** `backend/ledger.db` (transactions, accounts) and `backend/budgets.db` (budgets). Copy them while the app is stopped to back up.

### Env vars (source / self-hosted)

Desktop users can ignore this and use **Settings**. For source installs, edit `backend/.env` (see `backend/.env.example`):

| Setting | What it does |
| --- | --- |
| `PLAID_CLIENT_ID` | Plaid client ID |
| `PLAID_SANDBOX_SECRET` | Sandbox secret (`PLAID_ENV=sandbox`) |
| `PLAID_PROD_SECRET` | Production secret (`PLAID_ENV=production`) |
| `PLAID_ENV` | `sandbox` or `production` |
| `ENCRYPTION_KEY` | Encrypts stored bank tokens. Don't rotate after linking. |
| `ALCHEMY_API_KEY` | Optional Robinhood Chain wallets (or set in Settings) |
| `SYNC_INTERVAL_HOURS` | Auto-sync interval (default 6) |
| `RESEND_API_KEY` | Weekly summary email |
| `RESET_EMERGENCY_RESEND_API_KEY` | Email password reset |
| `PROPOSAL_SERVICE_KEY` | AI Advisor budget proposals |
| `ALERT_WEBHOOK_URL` | Slack / Discord / ntfy alerts |
| `CORS_ORIGINS` | Only if frontend and backend are on different origins |

### Troubleshooting (source)

| Problem | Fix |
| --- | --- |
| `command not found: python3` / `node` / `git` | Install the tool, or reopen the terminal. On Windows try `python` instead of `python3`. |
| `No module named ...` | Activate `.venv`, then `pip install -r requirements.txt`. |
| `:8000` connection refused | Backend isn't running. Check the uvicorn terminal. |
| Port 8000 already in use | `uvicorn main:app --port 8001` |
| PowerShell: "running scripts is disabled" | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then retry. |
| Plaid Link errors | Check `PLAID_CLIENT_ID` / `PLAID_SANDBOX_SECRET`, `PLAID_ENV=sandbox`, and that **Transactions** is enabled in the Plaid dashboard. [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md) |
| JSON or blank page instead of the UI | Build the frontend: `cd frontend && npm install && npm run build`, restart the backend. |

If **[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)** responds, the backend is fine and the problem is usually the frontend build.

---

## Security

This app holds bank connection data. A few hard rules:

- Don't expose it on the public internet. Use a VPN ([Tailscale](https://tailscale.com/) works well) if you need remote access.
- Access tokens are encrypted on disk and never sent to the browser.
- Keep `.env` and the `.db` files private. Store `ENCRYPTION_KEY` separately from database backups; together they unlock your bank link.
- Back up `ledger.db` and `budgets.db` regularly (copy while stopped, or `sqlite3 backend/ledger.db ".backup 'ledger-backup.db'"`).

Longer writeup: **[SECURITY.md](SECURITY.md)**.

---

## Docs

| Doc | Contents |
| --- | --- |
| [desktop/README.md](desktop/README.md) | Desktop app, updates, password recovery |
| [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md) | Plaid setup and production access |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the pieces fit together |
| [backend/MCP_SETUP.md](backend/MCP_SETUP.md) | Claude Desktop / AI Advisor |
| [SECURITY.md](SECURITY.md) | Threat model and hardening |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributing |

API docs while the backend is running: **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## License

[MIT](LICENSE)
