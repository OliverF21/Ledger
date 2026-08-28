"""
Cross-account transfer matching.

Pairs same-amount, opposite-sign transactions across different accounts —
either two bank Transaction rows (e.g. a checking outflow and a matching
credit-card payment posting) or a Transaction and an InvestmentTransaction
cash-deposit row (e.g. a checking outflow funding a Roth contribution) — and
persists the match. app.txn_classifier reads the persisted match as a
stronger-than-text-heuristic signal for the cash-flow role classifier.

A Transaction <-> Transaction match can only ever be a transfer or
credit-card payment: investment accounts aren't covered by Plaid's
/transactions/sync, so a genuine investment contribution never produces a
second Transaction row. That's why a Transaction <-> Transaction candidate
always outranks a Transaction <-> InvestmentTransaction candidate when a
transaction has both.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import InvestmentTransaction, Transaction
from app.services.returns_service import EXTERNAL_CASH_FLOW_SUBTYPES, EXTERNAL_CASH_FLOW_TYPES

_DATE_WINDOW_DAYS = 3
_TOLERANCE_FLOOR = 5.0
_TOLERANCE_PCT = 0.01


def _within_tolerance(amount_a: float, amount_b: float) -> bool:
    diff = abs(abs(amount_a) - abs(amount_b))
    tolerance = max(_TOLERANCE_FLOOR, max(abs(amount_a), abs(amount_b)) * _TOLERANCE_PCT)
    return diff <= tolerance


def _within_date_window(date_a: date, date_b: date) -> bool:
    return abs((date_a - date_b).days) <= _DATE_WINDOW_DAYS


def _opposite_sign(amount_a: float, amount_b: float) -> bool:
    return (amount_a > 0) != (amount_b > 0)


def _best_match(txn: Transaction, pool: dict[int, object]) -> object | None:
    """Closest-amount-then-closest-date match for `txn` among `pool`'s
    values. `pool` holds either Transaction or InvestmentTransaction rows;
    both expose .amount/.date, so the same scan works for either."""
    best = None
    best_key = None
    for other in pool.values():
        other_amount = float(other.amount)
        txn_amount = float(txn.amount)
        if not _opposite_sign(txn_amount, other_amount):
            continue
        if not _within_tolerance(txn_amount, other_amount):
            continue
        if not _within_date_window(txn.date, other.date):
            continue
        key = (abs(abs(txn_amount) - abs(other_amount)), abs((txn.date - other.date).days))
        if best is None or key < best_key:
            best, best_key = other, key
    return best


def match_transfers(db: Session, lookback_days: int = 10) -> dict:
    """
    Find and persist cross-account transfer matches among recent, unmatched
    transactions. Idempotent: only considers rows with no match set yet, so
    calling this repeatedly (e.g. every sync cycle) never re-touches
    already-matched rows. Commits once at the end. Returns
    {"transfer_pairs": int, "investment_pairs": int} for logging.
    """
    cutoff = date.today() - timedelta(days=lookback_days)

    bank_candidates = (
        db.query(Transaction)
        .filter(
            Transaction.removed.is_(False),
            Transaction.pending.is_(False),
            Transaction.date >= cutoff,
            Transaction.transfer_match_transaction_id.is_(None),
            Transaction.transfer_match_investment_txn_id.is_(None),
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    investment_candidates = [
        itxn
        for itxn in (
            db.query(InvestmentTransaction)
            .filter(
                InvestmentTransaction.type.in_(EXTERNAL_CASH_FLOW_TYPES),
                InvestmentTransaction.date >= cutoff,
                InvestmentTransaction.matched_transaction_id.is_(None),
            )
            .order_by(InvestmentTransaction.date.asc(), InvestmentTransaction.id.asc())
            .all()
        )
        # Plaid's subtype casing isn't guaranteed; normalize like
        # app.services.returns_service.external_cash_flows does.
        if (itxn.subtype or "").strip().lower() in EXTERNAL_CASH_FLOW_SUBTYPES
    ]

    unclaimed_bank = {txn.id: txn for txn in bank_candidates}
    unclaimed_investment = {itxn.id: itxn for itxn in investment_candidates}

    transfer_pairs = 0
    investment_pairs = 0

    for txn in bank_candidates:
        if txn.id not in unclaimed_bank:
            continue  # already claimed as someone else's counterpart this run

        same_account_excluded = {
            tid: t for tid, t in unclaimed_bank.items() if tid != txn.id and t.account_id != txn.account_id
        }
        bank_match = _best_match(txn, same_account_excluded)
        if bank_match is not None:
            txn.transfer_match_transaction_id = bank_match.id
            bank_match.transfer_match_transaction_id = txn.id
            del unclaimed_bank[txn.id]
            del unclaimed_bank[bank_match.id]
            transfer_pairs += 1
            continue

        investment_match = _best_match(txn, unclaimed_investment)
        if investment_match is not None:
            txn.transfer_match_investment_txn_id = investment_match.id
            investment_match.matched_transaction_id = txn.id
            del unclaimed_bank[txn.id]
            del unclaimed_investment[investment_match.id]
            investment_pairs += 1

    db.commit()
    return {"transfer_pairs": transfer_pairs, "investment_pairs": investment_pairs}
