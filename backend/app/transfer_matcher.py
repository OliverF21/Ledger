"""
Cross-account transfer matching.

Pairs same-amount, opposite-sign transactions across different accounts —
either two bank Transaction rows (e.g. a checking outflow and a matching
credit-card payment posting) or a bank outflow and an InvestmentTransaction
cash-deposit row (e.g. a checking outflow funding a Roth contribution) — and
persists the match. app.txn_classifier reads the persisted match as a
stronger-than-text-heuristic signal for the cash-flow role classifier.

Investment matching is funding-direction only (bank outflow → deposit).
A checking deposit landing from a brokerage withdrawal is left to the text
heuristic or a manual recategorization; auto-matching that pair would
permanently claim the investment row.

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

# Plaid PFC prefixes that mark a bank row as plausibly one leg of a transfer.
_TRANSFERISH_CATEGORY_PREFIXES = ("TRANSFER_", "LOAN_PAYMENTS")


def _looks_transferish(txn: Transaction) -> bool:
    """Does this bank row already carry a Plaid transfer/loan-payment signal?

    Without this precondition, the $5 tolerance floor lets any two small,
    unrelated opposite-sign rows on different accounts (e.g. an $8.25 coffee
    and a $4.10 refund) pair up and get permanently reclassified out of
    spending/income — the matcher never re-evaluates a pair once made.
    """
    for cat in (txn.category_plaid, txn.category_plaid_detailed):
        if cat and str(cat).upper().startswith(_TRANSFERISH_CATEGORY_PREFIXES):
            return True
    return (txn.transaction_code or "").strip().lower() == "transfer"


def _within_tolerance(amount_a: float, amount_b: float) -> bool:
    diff = abs(abs(amount_a) - abs(amount_b))
    tolerance = max(_TOLERANCE_FLOOR, max(abs(amount_a), abs(amount_b)) * _TOLERANCE_PCT)
    return diff <= tolerance


def _within_date_window(date_a: date, date_b: date) -> bool:
    return abs((date_a - date_b).days) <= _DATE_WINDOW_DAYS


def _opposite_sign(amount_a: float, amount_b: float) -> bool:
    return (amount_a > 0) != (amount_b > 0)


def _best_match(
    txn: Transaction, pool: dict[int, object], *, require_transferish: bool = False
) -> object | None:
    """Closest-amount-then-closest-date match for `txn` among `pool`'s
    values. `pool` holds either Transaction or InvestmentTransaction rows;
    both expose .amount/.date, so the same scan works for either.

    `require_transferish` is used for the bank<->bank pool only: at least one
    of the two legs must already look like a transfer. The investment pool
    needs no such guard — its candidates are already restricted to external
    cash-flow types/subtypes.
    """
    txn_is_transferish = _looks_transferish(txn) if require_transferish else False
    best = None
    best_key = None
    for other in pool.values():
        if require_transferish and not txn_is_transferish and not _looks_transferish(other):
            continue
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


def match_transfers(
    db: Session,
    lookback_days: int = 10,
    *,
    today: date | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Find and persist cross-account transfer matches among recent, unmatched
    transactions. Idempotent: only considers rows with no match set yet, so
    calling this repeatedly (e.g. every sync cycle) never re-touches
    already-matched rows. Commits once at the end. Returns
    {"transfer_pairs": int, "investment_pairs": int} for logging.

    `today` is injectable so callers (and tests) can pin the lookback window.
    With `dry_run=True` the matches are computed exactly as normal but never
    committed; the mutated ORM objects are simply left uncommitted for the
    caller's session lifecycle to discard.
    """
    cutoff = (today or date.today()) - timedelta(days=lookback_days)

    bank_candidates = (
        db.query(Transaction)
        .filter(
            Transaction.removed.is_(False),
            Transaction.pending.is_(False),
            Transaction.hidden.is_(False),
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
        # Amount < 0 is deposit-direction (money entering the investment
        # account). Withdrawals are out of scope this iteration.
        if (
            (itxn.subtype or "").strip().lower() in EXTERNAL_CASH_FLOW_SUBTYPES
            and float(itxn.amount) < 0
        )
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
        bank_match = _best_match(txn, same_account_excluded, require_transferish=True)
        if bank_match is not None:
            txn.transfer_match_transaction_id = bank_match.id
            bank_match.transfer_match_transaction_id = txn.id
            del unclaimed_bank[txn.id]
            del unclaimed_bank[bank_match.id]
            transfer_pairs += 1
            continue

        # Funding only: skip bank inflows so a checking deposit can't claim
        # a brokerage withdrawal via the opposite-sign check.
        if float(txn.amount) <= 0:
            continue
        investment_match = _best_match(txn, unclaimed_investment)
        if investment_match is not None:
            txn.transfer_match_investment_txn_id = investment_match.id
            investment_match.matched_transaction_id = txn.id
            del unclaimed_bank[txn.id]
            del unclaimed_investment[investment_match.id]
            investment_pairs += 1

    if dry_run:
        return {
            "transfer_pairs": transfer_pairs,
            "investment_pairs": investment_pairs,
            "dry_run": True,
        }

    db.commit()
    return {"transfer_pairs": transfer_pairs, "investment_pairs": investment_pairs}
