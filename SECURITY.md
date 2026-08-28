# Security Policy for Ledger

This document describes the threat model, security practices, and hardening guidelines for Ledger, a self-hosted personal finance dashboard.

> Ledger is provided "as is", without warranty, and is self-hosted — you operate and
> secure your own instance. See [DISCLAIMER.md](DISCLAIMER.md) and [TERMS.md](TERMS.md).

---

## Threat Model

### Assets to Protect
1. **Plaid Access Tokens** — grant read-only access to linked bank accounts
2. **Financial Transaction Data** — sensitive spending patterns and merchant information
3. **User Session** — authentication to the Ledger web UI
4. **Database** — contains encrypted tokens and transaction history

### Threat Scenarios

| Scenario | Risk | Mitigation |
|----------|------|-----------|
| **Attacker gains access to web server** | Can read plaintext tokens from memory or logs; access transactions | Encrypt tokens at rest; never log tokens; restrict network access |
| **Database is compromised** | Attacker reads all transactions; needs encryption key to decrypt tokens | Use encryption at rest; rotate encryption key if breached |
| **Plaid API key is leaked** | Attacker can create link tokens or call Plaid APIs | Rotate immediately; ensure key is in `.env` (gitignored) |
| **Session token is stolen** (XSS, shared machine) | Attacker can impersonate the user via `Authorization: Bearer` | Short TTL (`SESSION_TTL_DAYS`); HTTPS in production; don't expose app publicly; treat XSS as in-scope |
| **Backup is stolen** | All data exposed if encryption key is also stolen | Encrypt backups; store encryption key separately from backups |
| **Developer accidentally commits `.env`** | API keys exposed in git history | Use `.gitignore`, pre-commit hooks, and code review |

---

## Security Practices

### 1. Plaid Access Token Storage

**Requirement**: Access tokens **must never be stored or logged in plaintext**.

**Implementation**:
- Tokens are encrypted at rest using **Fernet** (AES-128-CBC + HMAC) from the `cryptography` library
- The encryption key (`ENCRYPTION_KEY`) is loaded from environment variables, never committed to git
- Tokens are decrypted only when making API calls to Plaid (in `plaid_service.py`)
- Decrypted tokens are never passed to the frontend or logged

**Key Rotation** (if `ENCRYPTION_KEY` is compromised):
1. Generate a new Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Decrypt all tokens with the old key and re-encrypt with the new key:
   ```python
   from cryptography.fernet import Fernet
   old_cipher = Fernet(old_key)
   new_cipher = Fernet(new_key)
   for item in db.query(Item):
       decrypted = old_cipher.decrypt(item.access_token_encrypted)
       item.access_token_encrypted = new_cipher.encrypt(decrypted)
   db.commit()
   ```
3. Update `ENCRYPTION_KEY` in production env vars
4. Delete old backups that contain tokens encrypted with the old key

### 2. Environment Variables & Secrets

**All sensitive values must be loaded from environment variables or `.env` files, never hardcoded.**

**Required Secrets**:
- `PLAID_CLIENT_ID` — Plaid client ID
- `PLAID_SANDBOX_SECRET` / `PLAID_PROD_SECRET` — Plaid secret, selected by `PLAID_ENV`
- `ENCRYPTION_KEY` — Fernet key for token encryption (also derives the session-token signing key unless `AUTH_TOKEN_KEY` is set)
- `DATABASE_URL` — Database connection string (includes password)

**Authentication**: a username/password account is created on first run (single-user, stored as a scrypt hash on the id=1 row). Login issues a Fernet-signed session token sent as `Authorization: Bearer` and held in `localStorage`; tokens expire after `SESSION_TTL_DAYS` (default 30). No credential is baked into the frontend bundle.

**Optional secrets**:
- `API_KEY` — legacy/automation credential accepted via the `X-API-Key` header. Leave unset to disable that path.
- `AUTH_TOKEN_KEY` — sign sessions with an independent key so `ENCRYPTION_KEY` can rotate without logging everyone out.

**Best Practices**:
- Use `.env.example` to document required variables with placeholder values
- Ensure `.env` is in `.gitignore` and never committed
- In CI/CD, inject secrets via platform secrets (GitHub Actions, Railway, Fly.io)
- Rotate all secrets annually or immediately if compromised
- Never print or log environment variable values

### 3. Plaid Environment Management

**Sandbox (Development)**:
- Set `PLAID_ENV=sandbox`
- Use Plaid's test credentials (provided in dashboard)
- Safe for development; no real accounts linked
- Test with sandbox test accounts before moving to production

**Production (Real Accounts)**:
- Only after Plaid approves your account (submit application via dashboard)
- Set `PLAID_ENV=production`
- Use production-only credentials (separate from sandbox)
- Never test in production; use sandbox for all testing
- Rotate credentials annually

### 4. Database Security

**Local Development** (SQLite):
- `sqlite:///ledger.db` is fine; no network exposure
- Include `*.db` in `.gitignore`

**Production** (PostgreSQL):
- Use a managed database service (AWS RDS, Railway, Fly.io Postgres)
- Enable encryption at rest in the database
- Use strong passwords (30+ random characters)
- Restrict network access (firewall rules, VPC isolation)
- Enable SSL/TLS for connections (`sslmode=require` in connection string)
- Set up regular automated backups with encryption
- **Never expose the database port to the public internet**

### 5. Frontend & Session Security

**Bearer tokens (not cookies)**:
- Login/register returns a Fernet-signed token stored in `localStorage`
  (`ledger_token`); `apiFetch()` sends it as `Authorization: Bearer`
- Tokens expire after `SESSION_TTL_DAYS` (default 30); expired tokens return
  401 and the UI redirects to login
- No credential is baked into the frontend bundle (unlike legacy `API_KEY` flows)
- **XSS risk**: a script injection could read `localStorage` — keep dependencies
  updated and do not expose the app to untrusted networks

**HTTPS in Production**:
- Always use HTTPS; redirect HTTP to HTTPS
- Obtain SSL certificates via Let's Encrypt (free) or your hosting provider
- Railway and Fly.io provide automatic HTTPS

**CORS Configuration**:
- Frontend and backend may be on different domains in production
- The `CORS_ORIGINS` env var (comma-separated) adds extra allowed origins on
  top of the localhost dev defaults in `backend/main.py` — set it to your
  production domain(s), never a wildcard
- The desktop app and single-port setups (backend serving the built frontend)
  are same-origin, so `CORS_ORIGINS` usually isn't needed at all

### 6. Network Security

**Access Control** (Self-Hosted on Your Network):
- Ledger is **single-user and intended for personal use**
- **Never expose to the public internet** — it contains all your financial data
- Run behind a firewall or VPN if accessed remotely
- Consider basic authentication or IP whitelisting for remote access

**Deployment Targets**:
- **Railway or Fly.io**: Use their built-in auth/firewall features
- **Home Server**: Keep on private network; use VPN for remote access (e.g., Tailscale, OpenVPN)
- **Cloud VPC**: Use security groups to allow only your IP addresses

### 7. Data Minimization

**What Ledger Stores**:
- Transaction data (amount, date, merchant, category)
- Account metadata (institution, account type, current balance)
- Encrypted Plaid access tokens (read-only, no money movement capability)

**What Ledger Does NOT Store**:
- User passwords in plaintext (only a scrypt hash on the `users` row)
- Bank login credentials (Plaid handles auth via Link flow)
- Personal identifiable information (PII) beyond what Plaid returns
- Payment/routing numbers or full account numbers (Plaid abstracts these)

### 8. Audit & Monitoring

**Logging**:
- Enable logs for authentication attempts and API errors
- **Never log**: access tokens, full credit card numbers, passwords
- Store logs with restricted access (not world-readable)
- Rotate log files after 30 days

**Monitoring** (Optional):
- Set up alerts for:
  - Failed login attempts (watch backend logs)
  - Large or unusual transactions (in-app alerts + optional `ALERT_WEBHOOK_URL`)
  - Sync job failures (indicates integration issue)
  - Database size growth (may indicate a data leak or bug)

---

## Hardening Checklist for Production

See [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) for the
full step-by-step runbook. Summary:

### Before First Deployment
- [ ] All secrets (Plaid keys, encryption key, DB password) are in env vars, NOT in code
- [ ] `.env` is in `.gitignore` and not committed to git
- [ ] Encryption key is generated with `Fernet.generate_key()` and stored securely
- [ ] `ENCRYPTION_KEY` (and optional `AUTH_TOKEN_KEY`) generated and stored securely
- [ ] Database uses PostgreSQL (not SQLite) with strong password
- [ ] Database is not exposed to the public internet (private VPC or firewall rules)
- [ ] HTTPS/SSL is enabled (Railway/Fly.io provides automatic)
- [ ] CORS is configured to allow only your frontend origin
- [ ] Plaid environment is set to `production` with production credentials (after approval)
- [ ] You have reviewed and understood the threat model (this document)

### Ongoing Maintenance
- [ ] Rotate secrets annually or after any suspected breach
- [ ] Keep Python, Node.js, and all dependencies up to date (run `pip install --upgrade -r requirements.txt` quarterly)
- [ ] Monitor for Plaid API deprecations or changes (check their changelog monthly)
- [ ] Review logs monthly for failed attempts or errors
- [ ] Back up the database weekly with encryption enabled
- [ ] Test restore procedure from backups at least quarterly
- [ ] Do not expose the Ledger URL publicly; use VPN or firewall rules for remote access

### If a Breach Occurs
1. **Immediate**:
   - Rotate all Plaid credentials immediately via [plaid.com/dashboard](https://plaid.com/dashboard)
   - Rotate `ENCRYPTION_KEY` (re-encrypt all tokens) and `API_KEY`
   - Invalidate all active sessions (requires code change: add logout-all endpoint)
   - Reset database user password

2. **Short-Term**:
   - Review logs for what was accessed and when
   - Check Plaid for unauthorized API calls
   - Notify yourself (or other stakeholders) of the breach and impact
   - Consider scanning for unauthorized Plaid Items (use `/items/list`)

3. **Long-Term**:
   - Implement additional monitoring (log aggregation, alerting)
   - Conduct a security audit of the codebase
   - Update this document with lessons learned

---

## Plaid-Specific Security

### Sandbox vs. Production
- **Sandbox**: Safe for development; use test credentials; no real accounts
- **Production**: Only after Plaid approval; uses real account data; requires production credentials

### Plaid Permissions
- The Ledger app requests **read-only** access via Plaid Link
- Users authorize this once per account during linking
- Ledger can fetch transactions and account info, but **cannot move money or change settings**

### Revoking Access
To unlink an account and revoke Ledger's access:
1. Delete the Item from Ledger (Settings → remove institution, or `DELETE /api/plaid/item/{id}`)
2. Plaid will automatically revoke the access token
3. Verify in Plaid's account settings that the app is no longer connected

### Plaid API Rate Limits
- Plaid has rate limits on API calls; monitor `/api/plaid/sync` and implement backoff if needed
- Ledger schedules syncs every 6 hours by default (configurable via `SYNC_INTERVAL_HOURS`)

---

## Incident Response

### Plaid Credential Leak
```bash
# Immediately rotate in Plaid dashboard:
# 1. Delete the old client_id and secret
# 2. Generate new ones
# 3. Update PLAID_CLIENT_ID and PLAID_SANDBOX_SECRET/PLAID_PROD_SECRET in your production env vars
# 4. Restart all services
```

### Encryption Key Leak
```bash
# Generate new key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Re-encrypt all tokens in the database (see "Key Rotation" section above)
# Update ENCRYPTION_KEY in env vars
# Restart all services
```

### Database Password Leak
```bash
# Immediately:
# 1. Change database password via your database provider
# 2. Update DATABASE_URL in env vars with new password
# 3. Restart backend service
# 4. Consider enabling database audit logs to detect unauthorized access
```

### API_KEY Leak (optional automation key only)
```bash
# Generate a new key:
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update API_KEY in backend/.env (or leave unset to disable X-API-Key entirely)
# Restart the backend. Normal browser login is unaffected.
```

---

## Security by Design

### No Hardcoded Credentials
All credentials are loaded from environment variables. The codebase contains no secrets.

### Encryption at Rest
Plaid tokens are encrypted using Fernet (authenticated encryption) before storing in the database.

### No Token Leakage
Tokens are never logged, printed, or sent to the frontend. They are decrypted only when calling Plaid APIs.

### Single-User Design
Ledger is built for single-user use. There is no multi-tenant isolation or per-user data segregation to bypass.

### Read-Only Access
Plaid integration uses read-only permissions. Ledger cannot move money or change account settings.

### Minimal Dependencies
Core dependencies (FastAPI, SQLAlchemy, `requests` for Plaid HTTP) are widely used. Fewer dependencies = smaller attack surface.

---

## Reporting Security Issues

If you discover a security vulnerability in Ledger:

1. **Do not** open a public GitHub issue.
2. Report it privately through GitHub's
   **[private vulnerability reporting](https://github.com/OliverF21/Ledger/security/advisories/new)**
   (repository **Security** tab → **Report a vulnerability**). Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
3. Please allow a reasonable time for a response and a fix before any public
   disclosure. Fixes, when made, are shipped as a new release and, where warranted,
   a published security advisory.

> **Maintainer setup (one-time):** the "Report a vulnerability" button only appears
> after enabling **Settings → Advanced Security → Private vulnerability reporting**
> on the GitHub repository. This cannot be enabled from the codebase.

---

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Plaid API Security](https://plaid.com/docs/api-security/)
- [Cryptography.io Fernet](https://cryptography.io/en/latest/fernet/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/sql-syntax.html#SQL-COMMANDS)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

---

**Last Updated**: 2026-07-15  
**Next Review**: Before any public deployment or auth model change
