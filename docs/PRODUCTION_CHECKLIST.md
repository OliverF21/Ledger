# Production Checklist

Ledger defaults to **Plaid Sandbox** (fake test banks). This checklist takes you from
Sandbox to connecting your **real** accounts, and covers hardening for an always-on
self-hosted deployment. Work top to bottom.

> Ledger is single-user software meant for your private network. **Do not expose it to
> the public internet.** See [SECURITY.md](../SECURITY.md) for the full threat model
> and [DISCLAIMER.md](../DISCLAIMER.md) for the terms under which you run it.

## 1. Get Plaid production access

- [ ] In the [Plaid dashboard](https://dashboard.plaid.com/), request production
      access and complete Plaid's application review.
- [ ] Enable the products you use: **Transactions**, **Auth**, and (optional)
      **Investments** — see [PLAID_SETUP.md](PLAID_SETUP.md).
- [ ] Copy your **production** secret (separate from the Sandbox secret).

## 2. Switch Ledger to production

In `backend/.env` (or via the in-app setup wizard / Settings → Plaid):

- [ ] Set `PLAID_ENV=production`.
- [ ] Set `PLAID_PROD_SECRET` to your production secret (keep `PLAID_SANDBOX_SECRET`
      for testing if you like — `PLAID_ENV` selects which is used).
- [ ] Confirm `PLAID_CLIENT_ID` is set.

## 3. Secrets

- [ ] `ENCRYPTION_KEY` is generated with `Fernet.generate_key()` and stored securely.
      **Never change it after linking an account** — it decrypts your stored Plaid
      tokens.
- [ ] Keep `ENCRYPTION_KEY` **separate from your database backups**; together they
      unlock your bank connection.
- [ ] `.env` is in `.gitignore` and never committed.
- [ ] (Optional) Set `AUTH_TOKEN_KEY` so you can rotate `ENCRYPTION_KEY` without
      logging out.

## 4. Data & backups

- [ ] Decide on storage: SQLite (default) is fine for single-user self-hosting. Use
      PostgreSQL (`DATABASE_URL`) only if you need concurrent writers.
- [ ] Set up regular backups of `ledger.db` and `budgets.db` (copy while the app is
      stopped, or `sqlite3 ledger.db ".backup 'ledger-backup.db'"`).
- [ ] Test restoring from a backup at least once.

## 5. Access & network

- [ ] The app is **not** reachable from the public internet.
- [ ] For remote access, use a private VPN (e.g. [Tailscale](https://tailscale.com/))
      rather than port-forwarding.
- [ ] If served over a network, terminate **HTTPS** in front of it and set
      `CORS_ORIGINS` to your exact origin(s) — never a wildcard.
- [ ] Consider a shorter `SESSION_TTL_DAYS` on shared machines.

## 6. Recovery

- [ ] Record the one-time **recovery code** shown at registration (it is always a
      valid password-reset path).
- [ ] (Optional) Set a **recovery email** in Settings and configure
      `RESET_EMERGENCY_RESEND_API_KEY` for email-based reset.

## 7. Verify

- [ ] Start the app; visit `/health`.
- [ ] Link one real account and run **Sync now**; confirm transactions appear.
- [ ] Confirm background sync runs (default every `SYNC_INTERVAL_HOURS`).

## 8. Ongoing

- [ ] Update dependencies periodically (`pip install --upgrade -r requirements.txt`;
      `npm install`).
- [ ] Rotate secrets annually or immediately after any suspected compromise (see
      [SECURITY.md](../SECURITY.md#if-a-breach-occurs)).
- [ ] Review logs occasionally for failed logins or sync errors.
