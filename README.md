# Ledger — Your Personal Finance Dashboard

Ledger is a private, self-hosted app that connects to your bank accounts and credit cards, automatically pulls in your transactions, and turns them into clean dashboards for spending, budgets, investments, and net worth. Everything runs **on your own computer** — your bank data never lives on someone else's server.

> **New to all this?** You do **not** need to be a programmer to run Ledger. This guide walks you through everything from scratch — installing the tools, getting the code, and starting the app — one copy-and-paste step at a time. Take it slow, and don't skip steps.

---

## 🚀 Quick start: download the desktop app

The fastest way to run Ledger — no Python, Node, or terminal required. Grab
the latest installer from **[Releases](https://github.com/OliverF21/Ledger/releases/latest)**:

- **macOS**: download the `.dmg`, drag Ledger into Applications
- **Windows**: download the `.exe` or `.msi` installer and run it

The app is unsigned (no Apple/Microsoft developer certificate), so the OS
will warn on first open:

- **Windows:** SmartScreen shows "Windows protected your PC" — click **More
  info → Run anyway**.
- **macOS:** open it once via **System Settings → Privacy & Security → “Open
  Anyway”**. If instead you see **"Ledger" is damaged and can't be opened**,
  that's a misleading Gatekeeper message for unsigned, browser-downloaded
  apps — it isn't actually corrupted. Fix it with:
  ```bash
  xattr -cr /Applications/Ledger.app
  ```

See [desktop/README.md](desktop/README.md#first-launch-unsigned-builds) for more detail.

Prefer to run from source, self-host on a server, or contribute code? Keep
reading below.

---

## Table of contents

1. [What Ledger can do](#1-what-ledger-can-do)
2. [How it works (the 30-second version)](#2-how-it-works-the-30-second-version)
3. [Before you start: the terminal](#3-before-you-start-the-terminal)
4. [Step 1 — Have the three tools installed](#4-step-1--have-the-three-tools-installed)
5. [Step 2 — Download Ledger](#5-step-2--download-ledger)
6. [Step 3 — Get your free Plaid keys](#6-step-3--get-your-free-plaid-keys)
7. [Step 4 — Create your settings file](#7-step-4--create-your-settings-file)
8. [Step 5 — Install Ledger's parts](#8-step-5--install-ledgers-parts)
9. [Step 6 — Start Ledger](#9-step-6--start-ledger)
10. [Step 7 — First-time setup in your browser](#10-step-7--first-time-setup-in-your-browser)
11. [Using Ledger day to day](#11-using-ledger-day-to-day)
12. [Troubleshooting](#12-troubleshooting)
13. [Optional extras](#13-optional-extras)
14. [Settings reference](#14-settings-reference)
15. [Security: please read](#15-security-please-read)
16. [More documentation](#16-more-documentation)

---

## 1. What Ledger can do


| Area              | What you get                                                                                                           |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Accounts**      | Securely link banks and credit cards; multiple institutions; sync on demand or automatically every few hours           |
| **Transactions**  | Search, filter, recategorize, split shared expenses, hide rows, export to a spreadsheet (CSV)                          |
| **Cash flow**     | Monthly income vs. spending, category breakdowns, flow diagrams                                                        |
| **Budgets**       | Monthly limits per category with progress bars and overage alerts                                                      |
| **Trends**        | 3 / 6 / 12 / 24-month spending patterns                                                                                |
| **Investments**   | Brokerage holdings and performance (needs the Plaid Investments product)                                               |
| **Subscriptions** | Automatic detection of recurring charges                                                                               |
| **Net worth**     | Daily balance snapshots that build a net-worth-over-time chart                                                         |
| **Alerts**        | In-app notifications, plus optional push to Slack / Discord / your phone                                               |
| **Weekly email**  | Optional spending-vs-budget summary in your inbox                                                                      |
| **AI Advisor**    | Claude (Anthropic's AI) can look at your finances and *suggest* budget changes — you approve or reject them in the app |


---

## 2. How it works (the 30-second version)

Ledger has two parts that run together on your computer:

- A **backend** (the engine) written in Python — it talks to your bank through a service called **Plaid** and stores your data in a local file.
- A **frontend** (the dashboards you see) written in React — the web pages you open in your browser.

You'll install both, then start the engine. Once it's running, you open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser and use the app like any website — except it's running entirely on your own machine.

**Plaid** is the trusted middleman that connects to thousands of banks. Ledger uses it so it never sees your bank password. Plaid is free to try in "Sandbox" mode (with fake test banks) before you connect real accounts.

---

## 3. Before you start: the terminal

Most steps below are typed into a **terminal** — a text window where you paste commands and press Enter.

- **macOS:** `Cmd + Space`, type **Terminal**, Enter.
- **Windows:** Start button, type **PowerShell**, open **Windows PowerShell**.

Throughout the guide, run the block labeled **🍎 macOS / Linux** or **🪟 Windows** to match your computer. (To paste: `Cmd + V` on Mac, right-click in PowerShell.)

---

## 4. Step 1 — Have the three tools installed

Ledger needs three free programs. If you already have them, skip ahead. Otherwise install each from its site — accept the defaults, then reopen your terminal.


| Tool             | What it's for                  | Download                                                  |
| ---------------- | ------------------------------ | --------------------------------------------------------- |
| **Python 3.11+** | Runs the backend engine        | [python.org/downloads](https://www.python.org/downloads/) |
| **Node.js 18+**  | Builds the dashboards          | [nodejs.org](https://nodejs.org/) (the **LTS** version)   |
| **Git**          | Downloads and updates the code | [git-scm.com/downloads](https://git-scm.com/downloads)    |


> **🪟 Windows:** in the Python installer, tick **"Add Python to PATH"** on the first screen.

Confirm they're available (each should print a version number):

```bash
python3 --version   # 🪟 Windows: python --version
node --version
git --version
```

---

## 5. Step 2 — Download Ledger

Pick a folder to keep Ledger in — your home folder is fine. In the terminal, run:

```bash
git clone https://github.com/OliverF21/ledger.git
cd ledger
```

The first line downloads the code into a new folder called `ledger`. The second line moves your terminal *into* that folder. **Every command from here on assumes you are inside the `ledger` folder.** If you open a new terminal later, run `cd ledger` again first (or `cd path/to/ledger`).

---

## 6. Step 3 — Get your free Plaid keys

Plaid is what lets Ledger read your transactions. You need three values from them. **Start in Sandbox mode** (fake test banks) — you can switch to your real bank later.

1. Create a free account at **[dashboard.plaid.com](https://dashboard.plaid.com/)**.
2. Go to **Team Settings → Keys**. You'll see:
  - **client_id**
  - **Sandbox** secret
3. Keep this browser tab open — you'll paste these into Ledger in the next step.

For the full walk-through (which Plaid products to turn on — **Transactions**, **Auth**, and **Investments** — and how to connect real banks later), see **[docs/PLAID_SETUP.md](docs/PLAID_SETUP.md)**.

---

## 7. Step 4 — Create your settings file

Ledger reads its secrets from a file called `backend/.env`. There's a ready-made template to copy.

**Copy the template:**

🍎 **macOS / Linux**

```bash
cp backend/.env.example backend/.env
```

🪟 **Windows (PowerShell)**

```powershell
copy backend\.env.example backend\.env
```

**Open `backend/.env` in a text editor** (TextEdit on Mac, Notepad on Windows, or [VS Code](https://code.visualstudio.com/) if you have it) and fill in these three things:

1. **Your Plaid keys** — paste the values from Step 3:
  ```
   PLAID_CLIENT_ID=paste_your_client_id_here
   PLAID_SANDBOX_SECRET=paste_your_sandbox_secret_here
   PLAID_ENV=sandbox
  ```
2. **An encryption key** — this scrambles your saved bank connection so it's safe on disk. Generate one by running this in your terminal:
  🍎 **macOS / Linux**
   🪟 **Windows**
  > If this command errors with "No module named cryptography," that's fine — it will work after Step 5. Come back and generate the key then.
   Copy the long line it prints and paste it after `ENCRYPTION_KEY=`:
   ⚠️ **Do not change this key after you've linked a bank account** — it's the only thing that can unlock your saved connection.
3. **Save the file.** Everything else in the file is optional and already has sensible defaults — you can ignore it for now.

---

## 8. Step 5 — Install Ledger's parts

This downloads the building blocks for both the engine and the dashboards. It only needs to be done once (and again whenever you update Ledger).

**Install the backend engine.** From inside the `ledger` folder:

🍎 **macOS / Linux**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

🪟 **Windows (PowerShell)**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
```

> **What is `.venv`?** It's a private, self-contained Python workspace for Ledger so it doesn't interfere with anything else on your computer. When it's active, your terminal prompt shows `(.venv)` at the start of the line.
>
> 🪟 **Windows note:** if `Activate.ps1` is blocked with a "running scripts is disabled" message, run this once, then try again:
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

**Install and build the dashboards:**

```bash
cd frontend
npm install
npm run build
cd ..
```

`npm install` downloads the frontend pieces (this can take a couple of minutes). `npm run build` turns them into the finished web pages the engine will serve.

---

## 9. Step 6 — Start Ledger

Now start the engine. Make sure your Python workspace is active (you should see `(.venv)` in your prompt — if not, re-run the activate line from Step 5).

🍎 **macOS / Linux**

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

🪟 **Windows (PowerShell)**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000
```

When you see a line like `Uvicorn running on http://0.0.0.0:8000`, Ledger is live. **Leave this terminal window open** — closing it stops the app.

Open your browser and go to:

### 👉 [http://127.0.0.1:8000](http://127.0.0.1:8000)

To stop Ledger later, click the terminal and press `Ctrl + C`.

---

## 10. Step 7 — First-time setup in your browser

1. **Create your account.** The first time you open Ledger it asks you to pick a username and password. This is *your* login for the app (single user). It's stored securely on your machine — there's no sign-up email, no cloud.
2. **Link a bank.** Go to **Settings → Connect account** and follow the Plaid pop-up.
  - In **Sandbox** mode, pick any test bank and use Plaid's test login: username `user_good`, password `pass_good`. ([Full sandbox credentials](https://plaid.com/docs/sandbox/test-credentials/).)
3. **Sync.** Click **Sync now** to pull in transactions. After that, Ledger also syncs automatically in the background every few hours (while the app is running).
4. **Explore** the **Overview**, **Transactions**, **Cash Flow**, **Budgets**, **Trends**, and **Investments** tabs.

That's it — you're running Ledger. 🎉

> Ready for real accounts? When you've tested with Sandbox, follow **[docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md)** to switch `PLAID_ENV` to production and connect your actual bank.

---

## 11. Using Ledger day to day

**Starting it again** after a reboot — open a terminal and run:

🍎 **macOS / Linux**

```bash
cd ledger/backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

🪟 **Windows**

```powershell
cd ledger\backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** again. (If you want it to stay on all the time without a terminal window, see [Always-on server](#always-on-home-server) below.)

**Updating Ledger** to the latest version:

```bash
cd ledger
git pull
cd backend && pip install -r requirements.txt && cd ..
cd frontend && npm install && npm run build && cd ..
```

(Activate your `.venv` first so `pip` installs into the right place.)

**Your data lives in** `backend/ledger.db` (transactions and accounts) and `backend/budgets.db` (budgets). Back these up by copying them somewhere safe — see [Security](#15-security-please-read).

---

## 12. Troubleshooting


| Symptom                                                 | Fix                                                                                                                                                                                                                |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `**command not found: python3` / `node` / `git`**       | The tool isn't installed or the terminal wasn't reopened after installing. Redo [Step 1](#4-step-1--have-the-three-tools-installed) and open a fresh terminal. On Windows try `python` instead of `python3`.       |
| `**No module named ...` when starting**                 | Your Python workspace isn't active or dependencies aren't installed. Re-run the activate line and `pip install -r requirements.txt` from [Step 5](#8-step-5--install-ledgers-parts).                               |
| **The page at :8000 won't load / "connection refused"** | The engine isn't running. Check the terminal from [Step 6](#9-step-6--start-ledger) is still open and shows "Uvicorn running."                                                                                     |
| **"Port 8000 is already in use"**                       | Ledger (or something else) is already using it. Close the other terminal, or start with a different port: `uvicorn main:app --port 8001` and open `http://127.0.0.1:8001`.                                         |
| **🪟 "running scripts is disabled on this system"**     | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then retry.                                                                                                                                        |
| **Plaid pop-up shows an error**                         | Double-check `PLAID_CLIENT_ID` / `PLAID_SANDBOX_SECRET` in `backend/.env`, that `PLAID_ENV=sandbox`, and that you enabled **Transactions** in the Plaid dashboard. See [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md). |
| **I see a page of JSON instead of the app**             | The dashboards weren't built. Run `npm run build` in the `frontend` folder ([Step 5](#8-step-5--install-ledgers-parts)) and restart the engine.                                                                    |
| **Blank page after `git pull`**                         | Rebuild the frontend: `cd frontend && npm install && npm run build`.                                                                                                                                               |


Still stuck? Open the interactive API status at **[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)** — if that loads, the engine is fine and the problem is the frontend build.

---

## 13. Optional extras

None of these are required to use Ledger. Set them up only if you want the feature.

### Alerts to your phone or chat

Add a webhook URL to `ALERT_WEBHOOK_URL` in `backend/.env` to get budget-overage and large-transaction alerts pushed to Slack, Discord, or [ntfy](https://ntfy.sh/).

### Weekly summary email

Get a free API key from [Resend](https://resend.com/) and set `RESEND_API_KEY` in `backend/.env`. Turn the email on and set the recipient in **Settings → Weekly email**.

### AI Advisor (Claude)

Ledger includes a local **MCP server** that lets [Claude Desktop](https://claude.ai/download) read your finances and *propose* budget changes. Claude can never change anything itself — proposals show up in the **Advisor** tab where you **Apply** or **Dismiss** them.

To enable it, set `PROPOSAL_SERVICE_KEY` in `backend/.env` (generate one with the same command style as the encryption key, using `secrets.token_urlsafe(32)`), then point Claude Desktop at Ledger. Full setup and example prompts: **[backend/MCP_SETUP.md](backend/MCP_SETUP.md)**.

### Import transactions from a CSV file

To bring in history from another app, use the command-line importer (a sample file, `backend/sample_import.csv`, shows the expected columns):

```bash
cd backend
python import_historical_data.py path/to/your-transactions.csv
```

### Developer mode (editing the dashboards)

If you want to change the frontend and see updates instantly, run the backend and a live frontend server in two terminals:

```bash
# Terminal 1
cd backend && uvicorn main:app --reload --port 8000
# Terminal 2
cd frontend && npm run dev
```

Then open **[http://localhost:5173](http://localhost:5173)** (it forwards data requests to the backend automatically).

### Always-on home server

- **Windows:** `scripts/install_ledger_service.ps1` registers Ledger as a service that starts at boot and restarts on crash. This is the recommended path if you also use the AI Advisor.
- **macOS/Windows:** the [desktop app](https://github.com/OliverF21/Ledger/releases/latest) runs Ledger as a native app with no terminal required — see [desktop/README.md](desktop/README.md) for first-launch notes.
- For remote access from your phone, use a private VPN like [Tailscale](https://tailscale.com/) rather than exposing the app to the public internet.

---

## 14. Settings reference

All settings live in `**backend/.env`** (copied from `backend/.env.example`, which has a comment explaining each one).

**Required for bank sync**


| Setting                | What it is                                                        |
| ---------------------- | ----------------------------------------------------------------- |
| `PLAID_CLIENT_ID`      | Your Plaid client ID                                              |
| `PLAID_SANDBOX_SECRET` | Plaid Sandbox secret (used when `PLAID_ENV=sandbox`)              |
| `PLAID_PROD_SECRET`    | Plaid Production secret (used when `PLAID_ENV=production`)        |
| `PLAID_ENV`            | `sandbox` (test banks) or `production` (real banks)               |
| `ENCRYPTION_KEY`       | Scrambles saved bank connections — **never change after linking** |


**Common optional settings**


| Setting                | What it is                                                           |
| ---------------------- | -------------------------------------------------------------------- |
| `SYNC_INTERVAL_HOURS`  | How often to auto-sync (default 6)                                   |
| `SESSION_TTL_DAYS`     | How long a login lasts before re-entering your password (default 30) |
| `DATABASE_URL`         | Where data is stored; default `sqlite:///ledger.db` (a local file)   |
| `ALERT_WEBHOOK_URL`    | Push alerts to Slack/Discord/ntfy                                    |
| `RESEND_API_KEY`       | Enables the weekly summary email                                     |
| `PROPOSAL_SERVICE_KEY` | Enables the AI Advisor's budget proposals                            |
| `CORS_ORIGINS`         | Only needed if the app and engine run on different addresses         |


The database schema is created and updated automatically on startup — there's no separate setup step.

---

## 15. Security: please read

Ledger holds sensitive financial data. Treat it like private infrastructure:

- **Don't put it on the public internet** without strong protection. For remote access, use a VPN like Tailscale.
- Your bank connection tokens are **encrypted at rest** and never shown to the browser.
- Keep `backend/.env` and your `.db` files private. **Store `ENCRYPTION_KEY` somewhere separate from your database backups** — together, they unlock your bank connection.
- Back up `backend/ledger.db` and `backend/budgets.db` regularly (just copy the files while the app is stopped, or use `sqlite3 backend/ledger.db ".backup 'ledger-backup.db'"`).

Full threat model and hardening checklist: **[SECURITY.md](SECURITY.md)**.

---

## 16. More documentation


| Document                                                     | What's inside                                      |
| ------------------------------------------------------------ | -------------------------------------------------- |
| [docs/PLAID_SETUP.md](docs/PLAID_SETUP.md)                   | Setting up Plaid and connecting real banks         |
| [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) | Going from Sandbox to your real accounts           |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)                 | How Ledger is built (for the curious / developers) |
| [backend/MCP_SETUP.md](backend/MCP_SETUP.md)                 | Connecting Claude Desktop (AI Advisor)             |
| [SECURITY.md](SECURITY.md)                                   | Security model and best practices                  |
| [CONTRIBUTING.md](CONTRIBUTING.md)                           | Contributing to the project                        |


When the engine is running, an interactive list of everything the backend can do is at **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## License

MIT — see [LICENSE](LICENSE). 

**Ledger — your money, your machine, your control.**