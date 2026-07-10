"""
Webhook delivery for alerts (Phase 4: budget overages & large transactions).

Opt-in via ALERT_WEBHOOK_URL. On each scheduled sync cycle, any alert not
already notified gets POSTed as JSON:

    {"text": "<human-readable summary>", "content": "<same>"}

"text" is understood by Slack-compatible receivers, "content" by Discord;
generic receivers (ntfy, Home Assistant, self-hosted relays) can read either.

Already-notified alerts are remembered in users.alerts_webhook_state (a JSON
list of keys) so a webhook fires once per alert: once per category per month
for budgets, once per transaction for large transactions. State is pruned to
the currently-active set, so it cannot grow unboundedly.
"""

import json
import logging
import os
from datetime import date

import requests
from sqlalchemy.orm import Session

from app.alerts import BudgetExceededItem, LargeTransactionItem, compute_active_alerts
from app.models import User

logger = logging.getLogger("ledger")

WEBHOOK_TIMEOUT_SECONDS = 10


def _format_lines(
    budget: list[BudgetExceededItem],
    large: list[LargeTransactionItem],
) -> str:
    lines = ["Ledger alerts:"]
    for b in budget:
        over = b.spent - b.limit
        lines.append(
            f"- Budget exceeded: {b.category} at ${b.spent:,.2f} of ${b.limit:,.2f} (${over:,.2f} over)"
        )
    for t in large:
        lines.append(f"- Large transaction: {t.merchant} ${t.amount:,.2f} on {t.date}")
    return "\n".join(lines)


def notify_new_alerts(db: Session, bdb: Session) -> int:
    """
    Compute active alerts, send the not-yet-notified ones to the webhook,
    and persist the notified set. Returns the number of alerts sent.
    No-op unless ALERT_WEBHOOK_URL is set.
    """
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return 0

    budget, large = compute_active_alerts(db, bdb)

    today = date.today()
    month_key = f"{today.year:04d}-{today.month:02d}"
    keyed_budget = {f"budget:{month_key}:{b.category}": b for b in budget}
    keyed_large = {f"txn:{t.id}": t for t in large}
    active_keys = set(keyed_budget) | set(keyed_large)

    user = db.query(User).filter(User.id == 1).first()
    try:
        notified: set[str] = set(json.loads(user.alerts_webhook_state or "[]"))
    except (ValueError, TypeError):
        notified = set()

    new_keys = active_keys - notified
    if new_keys:
        message = _format_lines(
            [b for k, b in keyed_budget.items() if k in new_keys],
            [t for k, t in keyed_large.items() if k in new_keys],
        )
        try:
            # Don't log the URL - Slack/Discord webhook URLs embed a secret token.
            response = requests.post(
                url,
                json={"text": message, "content": message},
                timeout=WEBHOOK_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Alert webhook delivery failed; will retry next sync cycle")
            return 0

    # Persist only after a successful send (or when nothing new): keep the
    # state pruned to currently-active alerts so it can't grow forever.
    new_state = json.dumps(sorted(active_keys))
    if new_state != (user.alerts_webhook_state or "[]"):
        user.alerts_webhook_state = new_state
        db.commit()

    if new_keys:
        logger.info("Sent %d alert(s) to webhook", len(new_keys))
    return len(new_keys)
