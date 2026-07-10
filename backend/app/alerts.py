"""
Active-alert computation, shared by the /settings/alerts/active endpoint
(in-app AlertsPanel) and the webhook notifier (app/notifications.py) so
both surfaces always agree on what counts as an alert.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Transaction, User
from app.routes.budgets import get_budget_items

# Documented defaults - _ensure_columns()'s ALTER TABLE ADD COLUMN carries no
# DEFAULT clause, so these columns are NULL on rows that existed before the
# columns were added. Never trust the ORM default having applied; always
# coalesce None to these values explicitly.
DEFAULT_BUDGET_EXCEEDED_ENABLED = True
DEFAULT_LARGE_TXN_ENABLED = False
DEFAULT_LARGE_TXN_THRESHOLD = 500.0

LARGE_TXN_WINDOW_DAYS = 7


@dataclass(frozen=True)
class AlertPrefsData:
    budget_exceeded_enabled: bool
    large_txn_enabled: bool
    large_txn_threshold: float


@dataclass(frozen=True)
class BudgetExceededItem:
    category: str
    spent: float
    limit: float


@dataclass(frozen=True)
class LargeTransactionItem:
    id: int
    merchant: str
    amount: float
    date: str


def get_alert_prefs(user: User) -> AlertPrefsData:
    return AlertPrefsData(
        budget_exceeded_enabled=(
            user.alert_budget_exceeded_enabled
            if user.alert_budget_exceeded_enabled is not None
            else DEFAULT_BUDGET_EXCEEDED_ENABLED
        ),
        large_txn_enabled=(
            user.alert_large_txn_enabled
            if user.alert_large_txn_enabled is not None
            else DEFAULT_LARGE_TXN_ENABLED
        ),
        large_txn_threshold=(
            float(user.alert_large_txn_threshold)
            if user.alert_large_txn_threshold is not None
            else DEFAULT_LARGE_TXN_THRESHOLD
        ),
    )


def compute_active_alerts(
    db: Session,
    bdb: Session,
) -> tuple[list[BudgetExceededItem], list[LargeTransactionItem]]:
    """
    Currently-active alerts, respecting each toggle's enabled state (empty
    list if disabled). No dismiss/acknowledge tracking - a budget-exceeded
    alert clears itself once spending or the limit changes, and a large
    transaction ages out of the trailing window on its own.
    """
    user = db.query(User).filter(User.id == 1).first()
    prefs = get_alert_prefs(user)

    budget_exceeded: list[BudgetExceededItem] = []
    if prefs.budget_exceeded_enabled:
        today = date.today()
        month_key = f"{today.year:04d}-{today.month:02d}"
        budget_items = get_budget_items(bdb, db, month_key)
        budget_exceeded = [
            BudgetExceededItem(category=b.category, spent=b.spent, limit=b.limit)
            for b in budget_items
            if b.spent > b.limit
        ]

    large_transactions: list[LargeTransactionItem] = []
    if prefs.large_txn_enabled:
        cutoff = date.today() - timedelta(days=LARGE_TXN_WINDOW_DAYS)
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.removed == False,
                Transaction.hidden == False,
                Transaction.pending == False,
                Transaction.date >= cutoff,
            )
            .order_by(Transaction.date.desc())
            .all()
        )
        for t in txns:
            eff = float(t.amount) * float(t.user_split_pct or 1)
            if eff > prefs.large_txn_threshold:
                large_transactions.append(LargeTransactionItem(
                    id=t.id,
                    merchant=t.merchant or "",
                    amount=round(eff, 2),
                    date=t.date.isoformat(),
                ))

    return budget_exceeded, large_transactions
