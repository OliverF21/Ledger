# Disclaimer

_Last updated: 2026-07-15_

Please read this before using Ledger. Using the software means you accept this
disclaimer, together with the [Terms of Use](TERMS.md) and
[Privacy notice](PRIVACY.md).

## Not financial or professional advice

Ledger is a personal bookkeeping and visualization tool. Nothing it shows — budgets,
trends, net-worth figures, subscription detection, or any suggestion from the
optional **AI Advisor** (powered by Anthropic's Claude) — is financial, investment,
tax, accounting, or legal advice. The AI Advisor's output is generated
automatically, may be wrong, and is informational only. Confirm with a qualified
professional before making any financial decision.

## Provided "as is" — no warranty — use at your own risk

Ledger is free, open-source software provided **"as is", without warranty of any
kind**, express or implied, as stated in the [MIT License](LICENSE). You run it
yourself, on your own hardware, at your own risk.

## No guarantee of accuracy

Your financial data comes from Plaid and your financial institutions. It may be
delayed, incomplete, mis-categorized, or wrong. Do not rely on Ledger as a system of
record — your bank and brokerage statements are authoritative.

## You run it; you are responsible for it

Ledger is **self-hosted** and runs entirely on your machine. You are responsible
for:

- securing the device Ledger runs on;
- safeguarding your secrets — especially `ENCRYPTION_KEY` and your Plaid keys;
- keeping backups of your data (`ledger.db` / `budgets.db`);
- keeping the app and its dependencies up to date;
- not exposing the app to the public internet.

The Ledger project operates no server, holds none of your data, and **cannot
recover** a lost database, a forgotten password, or a lost `ENCRYPTION_KEY`.

## Third-party services

Ledger connects to third-party services **on your behalf and under your own
accounts** — Plaid, your financial institutions, and optionally Resend (email),
GitHub (updates), and Anthropic/Claude (AI Advisor). Your use of each is governed by
that provider's own terms and privacy policy. The Ledger project is not a party to
those relationships and is not responsible for any provider's acts, omissions,
outages, or data breaches. See the [Privacy notice](PRIVACY.md) for what each
service receives.

## Unsigned software

Desktop builds ship **unsigned** (no Apple/Microsoft developer certificate). If you
follow the instructions to bypass your operating system's warnings, you do so at
your own risk. Only download Ledger from the official releases page:
<https://github.com/OliverF21/Ledger/releases>. Do not run builds obtained anywhere
else.

## Limitation of liability

To the maximum extent permitted by law, Ledger and its contributors are not liable
for any claim, loss, or damage — including loss of data, financial loss, or
unauthorized access to your self-hosted instance — arising from your use of, or
inability to use, the software. See the [MIT License](LICENSE) and the
[Terms of Use](TERMS.md).
