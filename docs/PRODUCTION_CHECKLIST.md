# Production Checklist: Sandbox → Real Financial Data

Step-by-step runbook for switching Ledger from Plaid Sandbox to real accounts
on a self-hosted / private-network deployment. See
[SECURITY.md](../SECURITY.md) for the full threat model and
[docs/PLAID_SETUP.md](PLAID_SETUP.md) for initial Plaid app setup.

**Everything in this doc is opt-in.** Nothing here activates until you set
`PLAID_ENV=production` and fill in `PLAID_PROD_SECRET` — until then the app
runs exactly as it does today, in sandbox, on SQLite.

---

## 0. What's already in place

- `PlaidService.validate_config()` fails fast at startup with a clear error
  if `PLAID_ENV=production` is set without `PLAID_CLIENT_ID` /
  `PLAID_PROD_SECRET` — you can't accidentally half-flip the switch.
- `CORS_ORIGINS` env var (comma-separated) adds extra allowed origins on top
  of the localhost dev defaults in [backend/main.py](../backend/main.py).
- `psycopg2-binary` is installed, so pointing `DATABASE_URL` at Postgres
  works with no code changes.
- `docker-compose.prod.yml` is a self-contained stack (Postgres + backend +
  Caddy) for a home-server deployment — no bind mounts, no `--reload`,
  Postgres port not published to the host, Caddy terminates HTTPS and
  reverse-proxies `/api`, `/docs`, `/health` to the backend while serving the
  built frontend for everything else.

None of this requires production Plaid credentials to exist or work — you
can run `docker-compose.prod.yml` today, still pointed at Plaid Sandbox, to
shake out the Postgres/Caddy setup before you ever touch real accounts.

---

## 1. Get Plaid production access

Pick one (see [docs/PLAID_SETUP.md](PLAID_SETUP.md) "Moving to Production"):

- **Full Production**: Dashboard → Settings → Compliance, submit the
  approval form (1–2 business days)
- **Trial plan** (brokerage-only, e.g. Robinhood, up to 10 Items): apply at
  [dashboard.plaid.com/trial-plan](https://dashboard.plaid.com/trial-plan)

Enable **Transactions**, **Auth**, and **Investments** products in the
dashboard before linking.

---

## 2. Provision Postgres

Using the bundled `docker-compose.prod.yml` Postgres service is the easiest
path (data stays on your host's Docker volume, never leaves the machine).
If you'd rather use a managed/external Postgres instead, set `DATABASE_URL`
to that instance's connection string with `sslmode=require` and skip the
`postgres` service in `docker-compose.prod.yml`.

Either way:
- Use a strong, random password (30+ chars) for `POSTGRES_PASSWORD`
- Never publish the Postgres port to the public internet
- Set up encrypted, scheduled backups + test a restore at least once

---

## 3. Generate production secrets

Do this **before** linking any real account — changing `ENCRYPTION_KEY`
after linking breaks decryption of stored tokens (see SECURITY.md "Key
Rotation" if you ever need to rotate it).

```bash
# ENCRYPTION_KEY — Fernet key for encrypting Plaid access tokens at rest
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# API_KEY (optional) — only if you need curl/automation via X-API-Key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Store `ENCRYPTION_KEY` somewhere separate from your database backups — a
stolen backup should be useless without it.

Fill in `.env` (see `.env.example`):
```
ENCRYPTION_KEY=<generated>
API_KEY=                  # optional; leave blank for session-only auth
POSTGRES_PASSWORD=<strong random password>
DOMAIN=<your domain, or leave as localhost if VPN/Tailscale-only>
CORS_ORIGINS=https://<your domain>   # only needed if frontend/backend are on different origins
```

---

## 4. Stand up the production stack (still on sandbox)

Worth doing as a dry run before touching Plaid production credentials:

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

Confirm the app is reachable through Caddy, Postgres is healthy, and a
sandbox sync still works end-to-end. This validates infra independently of
the Plaid cutover.

---

## 5. Flip the Plaid environment

1. In Plaid Dashboard → Settings → API Keys, copy your **Production**
   `client_id` and `secret`
2. Update `.env`:
   ```
   PLAID_CLIENT_ID=<production client id>
   PLAID_PROD_SECRET=<production secret>
   PLAID_ENV=production
   ```
3. Restart: `docker-compose -f docker-compose.prod.yml up -d`
   - If credentials are missing, the backend will refuse to start with a
     clear error (`PlaidService.validate_config()`) instead of failing
     silently later.
4. **Delete old sandbox Items** — sandbox access tokens don't work against
   production. From Settings in the UI, remove each linked sandbox account
   (or `DELETE /api/plaid/item/{item_id}`).
5. Decide on sandbox data: start fresh with a new Postgres database
   (cleanest), or leave the old sandbox transactions in place now that the
   Items are deleted (they'll just be orphaned history).

---

## 6. Re-link real accounts and verify

1. Link each real account via Plaid Link in Settings
2. Run a manual sync (`POST /api/plaid/sync` or the "Sync now" button) and
   confirm transactions appear
3. Check the Investments tab for brokerage accounts — if Plaid returns
   `ADDITIONAL_CONSENT_REQUIRED`, re-open Link in Update Mode for that Item
4. Robinhood cost basis may come back `null` for some positions — the UI
   shows "—" rather than erroring, this is expected

---

## 7. Harden network access

- Never expose Ledger to the public internet without network-level protection.
  Session login protects the API, but the app holds sensitive financial data —
  prefer VPN/Tailscale for remote access. See SECURITY.md.
- If you do want a login prompt in front of the whole app, uncomment the
  `basic_auth` block in [frontend/Caddyfile](../frontend/Caddyfile) and
  generate a hash with `docker run --rm caddy:2-alpine caddy hash-password`.
- Keep `CORS_ORIGINS` scoped to your actual domain, not a wildcard.

---

## 8. Ongoing

- Rotate Plaid credentials, `ENCRYPTION_KEY`, and `API_KEY` annually or
  immediately after any suspected leak (see SECURITY.md "Incident
  Response")
- Watch backend logs for sync failures / 401s / Plaid errors — there's no
  built-in alerting
- Test your backup restore procedure quarterly
