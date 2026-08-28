# Plaid Setup Guide

This guide walks you through setting up a Plaid account and configuring Ledger to use it.

---

## Step 1: Create a Plaid Account

1. Go to [plaid.com](https://plaid.com)
2. Click **Sign Up** (top right)
3. Fill in your details:
   - Email address
   - Password (strong, unique)
   - Company/Personal info
4. Verify your email
5. You're automatically placed in **Sandbox** mode (safe for testing)

---

## Step 2: Get Your API Credentials

1. Log in to [plaid.com/dashboard](https://plaid.com/dashboard)
2. In the left sidebar, click **Settings → API Keys**
3. You'll see two sections:
   - **Sandbox** (for development)
   - **Production** (for real accounts, requires approval)
4. For now, copy your **Sandbox** credentials:
   - `client_id` (looks like: `5e1234567890abcdef1234ab`)
   - `secret` (looks like: `abcd1234567890abcdef1234567890ab`)

### ⚠️ Important

- **Never share your `secret`.** It grants full API access to your account
- **Never commit credentials to git.** Use `.env` (gitignored)
- Regenerate credentials if you suspect they're leaked

---

## Step 3: Create `.env` File

1. In `backend/`, create a file named `.env`:
   ```bash
   cd backend
   cp .env.example .env
   ```

2. Edit `.env` and fill in your Plaid credentials:
   ```
   PLAID_CLIENT_ID=your_sandbox_client_id_here
   PLAID_SANDBOX_SECRET=your_sandbox_secret_here
   PLAID_ENV=sandbox
   ```

3. Generate the encryption key (required for Plaid token storage and session signing):
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. Paste into `.env`:
   ```
   ENCRYPTION_KEY=paste_generated_fernet_key_here
   ```

   `API_KEY` is **optional**, only needed for curl/automation via `X-API-Key`.
   Normal use relies on username/password login (no frontend `.env` required).

5. Also set:
   ```
   DATABASE_URL=sqlite:///ledger.db
   ```

Your `.env` should now look like:
```
PLAID_CLIENT_ID=5e1234567890abcdef1234ab
PLAID_SANDBOX_SECRET=abcd1234567890abcdef1234567890ab
PLAID_ENV=sandbox
ENCRYPTION_KEY=key_from_above
DATABASE_URL=sqlite:///ledger.db
LOG_LEVEL=INFO
SYNC_INTERVAL_HOURS=6
```

---

## Step 4: Enable Plaid Products

Ledger uses these Plaid products:

1. **Transactions**: transaction history and balances
2. **Auth**: account verification (recommended)
3. **Investments**: brokerage holdings (required for the Investments tab; see Step 4b)

To enable them:

1. Go to [plaid.com/dashboard](https://plaid.com/dashboard)
2. In the left sidebar, click **Settings → Products**
3. Under **Sandbox**:
   - Toggle **ON** for `Transactions`
   - Toggle **ON** for `Auth` (optional)
4. Click **Save**

### What Each Product Does

| Product | Purpose | Cost |
|---------|---------|------|
| **Transactions** | Fetch past and current transactions | Free in Sandbox |
| **Auth** | Verify account ownership and get account numbers | Free in Sandbox |
| **Identity** | Get user's personal info (name, email, address) | Not needed for Ledger |
| **Balance** | Get real-time account balances | Included with Transactions |

---

## Step 4b: Enable Investments (for the Investments tab)

Ledger's **Investments** tab (position-level brokerage holdings, e.g. Robinhood) needs
the Investments product enabled in addition to Transactions/Auth:

1. Go to [plaid.com/dashboard](https://plaid.com/dashboard) → **Settings → Products**
2. Under **Sandbox**, toggle **ON** for `Investments`
3. Click **Save**

`plaid_service.py` requests `transactions` as the required product, with `investments` in
`required_if_supported_products` (Robinhood gets holdings; banks like Capital One link
without it). Do not put `investments` in the main `products` array. That blocks banks
that don't offer brokerage accounts.

### OAuth banks (Chase, Robinhood, Capital One, …): no setup required

Most major US banks (Chase, Bank of America, Wells Fargo, Capital One, Citi, Robinhood,
SoFi, …) use **OAuth**: they send you to the bank's own site to log in, then redirect
back. Ledger uses Plaid **Hosted Link** for this, so **you do not configure a redirect
URI, and you do not need ngrok**. Plaid hosts the entire Link flow (including the OAuth
redirect) on its own HTTPS domain.

What happens when you link or update a bank:

1. Click **+ Link new account** (or **Update connection**) in Settings.
2. A secure Plaid page opens in your **system browser**; log in / complete OAuth there.
3. Ledger polls in the background and updates automatically when you finish. No
   redirect back into the app is needed.

Hosted Link requires no special Plaid Dashboard enablement and no `PLAID_REDIRECT_URI`.
This is what lets the packaged desktop app (served at `http://127.0.0.1`) link OAuth
banks at all. Plaid rejects non-HTTPS redirect URIs in production, so the old
in-webview redirect approach could never work there.

### Sandbox: custom user with brokerage holdings

The standard `user_good` / `pass_good` sandbox login has no investment accounts. To test
holdings, create a **custom sandbox user** instead:

1. Dashboard → **Developers → Sandbox** → create a custom user
2. Give it an `investment` / `brokerage` account with real tickers (e.g. `AAPL`, `VOO`,
   `BTC`). See [plaid.com/docs/sandbox/user-custom](https://plaid.com/docs/sandbox/user-custom/)
3. Robinhood exists as a sandbox institution but only supports the `brokerage` subtype
   (not `variable annuity`). Pick `brokerage` when configuring the custom user

### Real Robinhood data (Trial plan)

Robinhood is a real institution on Plaid's network (OAuth-based Link flow), but pulling
**real** holdings requires Production API access:

1. Apply for the free **Trial plan** at [dashboard.plaid.com/trial-plan](https://dashboard.plaid.com/trial-plan)
   (US/Canada, up to 10 Production Items; Investments + Investments Refresh included)
2. Trial uses **Production** API keys. Set `PLAID_ENV=production` and fill in
   `PLAID_PROD_SECRET`
3. **Robinhood uses OAuth**, but Ledger links it via Plaid **Hosted Link**. The OAuth
   flow opens in your system browser on Plaid's HTTPS domain, so **no redirect URI,
   ngrok, or HTTPS setup is required** (see "OAuth banks" above). Just click **+ Link
   new account** and finish in the browser tab that opens.
4. If an account was linked *before* `investments` was added to the Link token's
   `products`, it must be **re-linked in Update Mode** (Plaid returns
   `ADDITIONAL_CONSENT_REQUIRED`). Re-open Plaid Link for that item to grant consent
6. Cost basis may come back `null` for some Robinhood positions. The Investments tab
   shows "-" in the Gain column in that case rather than erroring

Orphan Items created by failed link attempts still count against your trial quota. Remove
them in [Plaid Dashboard → Items](https://dashboard.plaid.com/activity/items) before
retrying.

---

## Step 5: Test with Sandbox Credentials

Plaid provides test credentials you can use to simulate linked accounts:

### Test Credentials (Sandbox Only)

Use these to test Ledger's account linking flow:

| Credential | Value | Notes |
|---|---|---|
| **Username** | `user_good` | Simulates successful account link |
| **Password** | `pass_good` | Always works in Sandbox |
| **2FA/MFA** | (if prompted) | Enter any 6-digit code, e.g., `123456` |

### Test Institutions

In Plaid Link, search for any of these and use the test credentials above:

- **Platypus Bank** (simple, no MFA)
- **Chase** (popular, tests multiple account types)
- **Wells Fargo** (tests credit card linking)
- **Citibank** (tests savings accounts)

All test institutions use `user_good` / `pass_good`.

---

## Step 6: Run Ledger Locally

1. Start the backend and frontend (see README.md "Local Development"):
   ```bash
   # Terminal 1
   cd backend && uvicorn main:app --reload --port 8000
   # Terminal 2
   cd frontend && npm run dev
   ```

2. Wait for the backend to be ready (you'll see logs like `✅ Ledger backend started`)

3. Open http://localhost:5173 in your browser

4. Click **"Connect Account"** (or similar button, depending on UI progress)

5. Plaid Link modal will open; use test credentials:
   - Username: `user_good`
   - Password: `pass_good`

6. Select an institution (e.g., Platypus Bank)

7. Authorize Ledger to access the account

8. You should see the account appear in Ledger's account list

9. Transactions will sync (either automatically or click "Sync Now")

---

## Step 7: Verify the Integration

### Check Backend Logs

Check the terminal running `uvicorn`. You should see:
```
✅ Ledger backend started
...
[info] Syncing transactions for item: ...
[info] Fetched X transactions
```

### Check Database

```bash
# If using SQLite (default):
sqlite3 ledger.db "SELECT * FROM items;"

# If using PostgreSQL (DATABASE_URL points at it):
psql "$DATABASE_URL" -c "SELECT * FROM items;"
```

You should see a row with your linked account.

### Check Frontend

- Go to http://localhost:5173
- You should see your linked account listed
- Transactions should appear in the transaction feed

---

## Moving to Production (Later)

Once you're ready to use **real** bank accounts:

1. **Request Production Access**:
   - Go to [plaid.com/dashboard](https://plaid.com/dashboard)
   - Click **Settings → Compliance**
   - Complete the approval form (Plaid will ask about your app, how you'll handle data, etc.)
   - Plaid approves you within 1-2 business days

2. **Generate Production Credentials**:
   - Once approved, go to **Settings → API Keys**
   - Copy your **Production** `client_id` and `secret` (different from Sandbox)

3. **Update `.env`**:
   ```
   PLAID_CLIENT_ID=your_production_client_id
   PLAID_PROD_SECRET=your_production_secret
   PLAID_ENV=production
   ```

4. **Restart Ledger** so it picks up the new `.env` values.

5. **Link Real Accounts**:
   - In Plaid Link, search for your actual bank
   - Log in with your real credentials (Plaid never sees your password; they use OAuth)
   - Authorize Ledger

⚠️ **Warning**: Once in Production, be careful:
- Your real transaction data will be stored in the database
- Rotate credentials if compromised
- Keep backups encrypted
- Run on a secure server (never expose publicly without auth)

---

## Troubleshooting

### "Invalid client_id or secret"

- Check that `PLAID_CLIENT_ID` and `PLAID_SANDBOX_SECRET`/`PLAID_PROD_SECRET` are correctly copied (no extra spaces)
- Ensure you're using **Sandbox** credentials if `PLAID_ENV=sandbox`
- Ensure you're using **Production** credentials if `PLAID_ENV=production`
- If unsure, regenerate credentials in [plaid.com/dashboard](https://plaid.com/dashboard)

### "Transactions product not enabled"

- Go to [plaid.com/dashboard](https://plaid.com/dashboard)
- Click **Settings → Products**
- Make sure **Transactions** is toggled ON

### "Link token creation failed"

- Check the terminal running `uvicorn` for backend logs
- Verify `PLAID_CLIENT_ID` and `PLAID_SANDBOX_SECRET`/`PLAID_PROD_SECRET` are in `.env`
- Verify `PLAID_ENV` is set to `sandbox` or `production` (not misspelled)

### "Account link succeeded but no transactions appear"

- Go to http://localhost:8000/docs (API documentation)
- Use `POST /api/plaid/sync` (authorize with Bearer token from login)
- Wait 10-30 seconds for transactions to sync
- Refresh http://localhost:5173 to see transactions

### "Plaid Link is stuck or slow"

- This is normal in Sandbox (Plaid's test environment can be slow)
- Try a different browser or clear cookies
- If in Production, check your internet connection

### "I want to unlink an account"

1. Go to [plaid.com/dashboard](https://plaid.com/dashboard)
2. Click **Connected Apps** (left sidebar)
3. Find "Ledger" and click **Disconnect**
4. This revokes Ledger's access; the account will also disappear from Ledger

---

## Rate Limits

Plaid has rate limits on API calls:

- **Free/Sandbox**: 100 requests per minute
- **Production**: Depends on your plan

Ledger syncs transactions every 6 hours by default, which is well within limits.

---

## FAQ

### Q: Can Ledger access all my accounts?

**A**: Only the accounts you explicitly authorize via Plaid Link. You're in full control.

### Q: Can Ledger move money?

**A**: No. Ledger has read-only access. It can only fetch data, not perform transactions.

### Q: Does Ledger store my password?

**A**: No. You log into your bank directly via Plaid's secure link. Plaid passes a token to Ledger; your password is never shared.

### Q: What happens if I revoke access in my bank's app?

**A**: Plaid will automatically stop being able to fetch transactions. Ledger will fail to sync and show an error.

### Q: Can I use Ledger without Plaid?

**A**: Not currently. Plaid is the primary data source. You could theoretically extend Ledger to support manual data entry, but that's out of scope for now.

### Q: Is Plaid free?

**A**: Sandbox (testing) is free. Production pricing depends on your usage and plan. See [plaid.com/pricing](https://plaid.com/pricing).

---

## Next Steps

Once Plaid is set up:

1. Start the app (`uvicorn` with the built frontend, or the desktop app)
2. **Create your account** on first visit (username + password)
3. **Settings → Connect account**: link a Sandbox institution
4. **Sync now**: pull transactions and balances
5. Explore Overview, Transactions, Cash Flow, Budgets, Investments, Trends,
   Subscriptions, and Settings

See [README.md](../README.md) and [docs/ARCHITECTURE.md](ARCHITECTURE.md) for the
full feature list and API overview.

---

**Last Updated**: 2026-07-06  
**Plaid Docs**: [plaid.com/docs](https://plaid.com/docs)
