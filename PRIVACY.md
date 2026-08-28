# Privacy & Data Handling

*Last updated: 2026-07-15*

**Short version: the Ledger project cannot leak data it never receives.** Ledger is self-hosted software that runs entirely on your computer. The project operates no server, runs no database except for the one you run off your machine, includes no analytics or telemetry, and has no way to see, collect, or access your data or your usage.

This notice explains where your data lives and which third parties **your own copy**
of Ledger talks to. It describes the software as of the date above; a future version
could change what leaves your machine, in which case this notice will be updated.

## What the Ledger project collects

Nothing. There is no account to create with us, no cloud sync, no crash reporting,
no usage analytics, and no "phone home". The only infrastructure the project runs is
its public GitHub repository, which hosts the source code and the downloadable
releases.

## Where your data lives

All of your data is stored in local database files on your own disk (the Plaid
access tokens inside them are individually encrypted at rest):

- **Desktop app:** the OS application-data directory —
`~/Library/Application Support/Ledger/` (macOS) or `%APPDATA%\Ledger\` (Windows).
- **Running from source:** `backend/ledger.db` and `backend/budgets.db`.

It never leaves your machine except to the third parties listed below, and only for
the features you use.

## Third parties your instance contacts


| Service                                   | When                                                        | What leaves your machine                                                                       | Whose account       |
| ----------------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------- |
| **Plaid**                                 | Linking a bank and every sync                               | Requests using *your* Plaid keys; Plaid returns your transactions/balances                     | Your Plaid account  |
| **Your bank / brokerage**                 | Via Plaid, when linking/syncing                             | Handled by Plaid; Ledger never sees your bank login                                            | Yours               |
| **GitHub**                                | Desktop app launch (update check) and downloads             | A version check and, if updating, the download request — exposes your IP to GitHub             | n/a                 |
| **Google Fonts** (`fonts.googleapis.com`) | Loading the web UI                                          | A font request — exposes your IP to Google                                                     | n/a                 |
| **Resend** (optional)                     | Only if you enable the weekly email or email password-reset | The email and *your* Resend API key                                                            | Your Resend account |
| **Alert webhook** (optional)              | Only if you set `ALERT_WEBHOOK_URL`                         | Alert text to the Slack/Discord/ntfy URL you chose                                             | Yours               |
| **Anthropic / Claude** (optional)         | Only if you use the AI Advisor via Claude Desktop           | Whatever your local Claude Desktop sends; the Ledger backend sends nothing to Anthropic itself | Your Claude account |


Ledger sets no tracking cookies and embeds no third-party advertising or analytics.
Outbound *links* you choose to click (documentation, the donation link) take you to
those sites under their own policies.

## Shared responsibility

Because Ledger is self-hosted, **you are the operator and data controller of your own
instance.** If any data-protection law (such as the GDPR or CCPA) applies to your
use, the responsibilities it imposes on a controller are yours, not the Ledger
project's. Practically, that means securing your machine, your keys, and your
backups — see the [Disclaimer](DISCLAIMER.md) and [SECURITY.md](SECURITY.md).

## Questions

Because the project holds none of your data, there is nothing for us to export or
delete on your behalf. For questions about the software itself, open an issue on the
GitHub repository.