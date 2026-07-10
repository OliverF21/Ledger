"""
Recurring-transaction (subscription) detection.

Computed live from Transaction rows on each request, same pattern as
routes/budgets.py::suggest_budgets() - no new table, so there's nothing to
keep in sync with sync_engine.py and no extra migration.

Heuristic, not exact: merchant-name normalization and cadence/amount
tolerances are approximate. May occasionally over-merge distinct merchants
or miss genuinely recurring charges with irregular billing.
"""

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Transaction

TRAILING_MONTHS = 12
MIN_OCCURRENCES = 3

WEEKLY_DAYS = 7
WEEKLY_TOLERANCE = 2
MONTHLY_DAYS = 30
MONTHLY_TOLERANCE = 5
ANNUAL_DAYS = 365
ANNUAL_TOLERANCE = 15

AMOUNT_TOLERANCE_PCT = 0.15

# Ordered (cadence, expected_days, tolerance_days) - checked in this order,
# first match wins. Weekly before monthly before annual.
_CADENCES = [
    ("weekly", WEEKLY_DAYS, WEEKLY_TOLERANCE),
    ("monthly", MONTHLY_DAYS, MONTHLY_TOLERANCE),
    ("annual", ANNUAL_DAYS, ANNUAL_TOLERANCE),
]

_TRAILING_NUMERIC_SUFFIX = re.compile(r"[\s#*_-]*\d{3,}[\d\s*-]*$")
_WHITESPACE = re.compile(r"\s+")


def normalize_merchant(merchant: str) -> str:
    """
    Lowercase, strip trailing store/phone-number-like digit runs, collapse
    whitespace. Approximate - e.g. "Amazon #1234" and "NETFLIX.COM 8005852328"
    both normalize to a stable grouping key, but this can occasionally merge
    or split merchants a human wouldn't.
    """
    name = (merchant or "").strip().lower()
    name = _TRAILING_NUMERIC_SUFFIX.sub("", name)
    name = _WHITESPACE.sub(" ", name).strip()
    return name


@dataclass
class RecurringSeries:
    merchant: str
    category: str
    cadence: str
    average_amount: float
    last_date: date
    next_expected_date: date
    occurrence_count: int


def _classify_cadence(gaps: list[int]) -> tuple[str, int] | None:
    """Return (cadence, expected_days) if gaps are consistent with a known
    cadence (median close to a known interval, individual gaps not too far
    from that median), else None."""
    if not gaps:
        return None
    median_gap = statistics.median(gaps)
    for cadence, expected_days, tolerance in _CADENCES:
        if abs(median_gap - expected_days) > tolerance:
            continue
        if all(abs(gap - median_gap) <= tolerance for gap in gaps):
            return cadence, expected_days
    return None


def _most_common_category(txns: list[Transaction]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for t in txns:
        counts[t.display_category or "Uncategorized"] += 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def detect_recurring_series(db: Session, months: int = TRAILING_MONTHS) -> list[RecurringSeries]:
    """Detect recurring (subscription-like) charges over the trailing window."""
    cutoff = date.today() - timedelta(days=months * 31)

    txns = (
        db.query(Transaction)
        .filter(
            Transaction.removed == False,
            Transaction.hidden == False,
            Transaction.amount > 0,
            Transaction.date >= cutoff,
        )
        .order_by(Transaction.date.asc())
        .all()
    )

    groups: dict[str, list[Transaction]] = defaultdict(list)
    for t in txns:
        key = normalize_merchant(t.merchant or "")
        if key:
            groups[key].append(t)

    results: list[RecurringSeries] = []
    for group_txns in groups.values():
        if len(group_txns) < MIN_OCCURRENCES:
            continue

        group_txns.sort(key=lambda t: t.date)
        dates = [t.date for t in group_txns]
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]

        cadence_result = _classify_cadence(gaps)
        if cadence_result is None:
            continue
        cadence, expected_days = cadence_result

        amounts = [float(t.amount) * float(t.user_split_pct or 1) for t in group_txns]
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount <= 0:
            continue
        if any(abs(a - avg_amount) > avg_amount * AMOUNT_TOLERANCE_PCT for a in amounts):
            continue

        last_txn = group_txns[-1]
        results.append(RecurringSeries(
            merchant=last_txn.merchant or "",
            category=_most_common_category(group_txns),
            cadence=cadence,
            average_amount=round(avg_amount, 2),
            last_date=last_txn.date,
            next_expected_date=last_txn.date + timedelta(days=expected_days),
            occurrence_count=len(group_txns),
        ))

    results.sort(key=lambda r: r.average_amount, reverse=True)
    return results
