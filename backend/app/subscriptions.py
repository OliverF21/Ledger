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

from app.analytics_shared import (
    budget_parent_key,
    category_key_for_spending_rules,
    is_excluded_from_budget_spending,
)
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
    merchant_key: str
    category: str
    parent_key: str | None
    cadence: str
    average_amount: float
    first_date: date
    last_date: date
    next_expected_date: date
    expected_days: int
    occurrence_count: int
    occurrence_dates: tuple[date, ...]
    budget_eligible: bool


@dataclass
class RecurringBudgetLine:
    """Expected recurring spend to reserve in one calendar month."""

    merchant_key: str
    merchant: str
    category: str
    parent_key: str | None
    cadence: str
    expected_amount: float


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


def _most_common_parent(txns: list[Transaction]) -> str | None:
    counts: dict[str, int] = defaultdict(int)
    for t in txns:
        parent = budget_parent_key(t.category_user, t.category_plaid, t.category_plaid_detailed)
        if parent:
            counts[parent] += 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _is_budget_eligible(txns: list[Transaction]) -> bool:
    """True when the series is consumptive spend, not transfers or loan payments.

    A single miscategorized charge should not hide a real subscription, and a
    transfer that happens to repeat should not become a spending budget.
    """
    if not txns:
        return False
    eligible = 0
    for t in txns:
        key = category_key_for_spending_rules(
            t.category_user, t.category_plaid, t.category_plaid_detailed
        )
        if not is_excluded_from_budget_spending(key):
            eligible += 1
    return eligible * 2 >= len(txns)


def _cadence_tolerance(cadence: str) -> int:
    for name, _expected_days, tolerance in _CADENCES:
        if name == cadence:
            return tolerance
    return MONTHLY_TOLERANCE


def _projected_dates(
    anchor: date,
    step: int,
    start: date,
    end: date,
    earliest: date,
    latest: date,
) -> list[date]:
    """Dates `anchor + k*step` inside [start, end), clamped to [earliest, latest)."""
    if step <= 0 or end <= start:
        return []
    window_start = max(start, earliest)
    window_end = min(end, latest)
    if window_end <= window_start:
        return []
    delta = (window_start - anchor).days
    if delta <= 0:
        k = -((-delta) // step)
    else:
        k = (delta + step - 1) // step
    dates: list[date] = []
    for _ in range(48):
        current = anchor + timedelta(days=k * step)
        if current >= window_end:
            break
        if current >= window_start:
            dates.append(current)
        k += 1
    return dates


def _charges_budgeted_in_month(
    series: RecurringSeries,
    start: date,
    end: date,
    as_of: date,
) -> int:
    """How many charges to reserve in [start, end).

    Monthly and annual series reserve one bill in a month where a charge is
    expected or already posted, and more only when more than one actually
    posted. Weekly series reserve each projected (or posted) occurrence.
    A lapsed series is not projected past the missed cycle.
    """
    tolerance = _cadence_tolerance(series.cadence)
    active = as_of <= series.next_expected_date + timedelta(days=tolerance)
    latest = end if active else min(end, series.next_expected_date + timedelta(days=tolerance + 1))
    projected = _projected_dates(
        series.last_date,
        series.expected_days,
        start,
        end,
        series.first_date,
        latest,
    )
    actual = [d for d in series.occurrence_dates if start <= d < end]
    if series.cadence == "weekly":
        return max(len(projected), len(actual))
    if not projected and not actual:
        return 0
    return max(1, len(actual))


def detect_recurring_series(
    db: Session,
    months: int = TRAILING_MONTHS,
    as_of: date | None = None,
) -> list[RecurringSeries]:
    """Detect recurring (subscription-like) charges over the trailing window."""
    today = as_of or date.today()
    cutoff = today - timedelta(days=months * 31)

    txns = (
        db.query(Transaction)
        .filter(
            Transaction.removed == False,
            Transaction.hidden == False,
            Transaction.amount > 0,
            Transaction.date >= cutoff,
            Transaction.date <= today,
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
            merchant_key=normalize_merchant(last_txn.merchant or ""),
            category=_most_common_category(group_txns),
            parent_key=_most_common_parent(group_txns),
            cadence=cadence,
            average_amount=round(avg_amount, 2),
            first_date=group_txns[0].date,
            last_date=last_txn.date,
            next_expected_date=last_txn.date + timedelta(days=expected_days),
            expected_days=expected_days,
            occurrence_count=len(group_txns),
            occurrence_dates=tuple(t.date for t in group_txns),
            budget_eligible=_is_budget_eligible(group_txns),
        ))

    results.sort(key=lambda r: r.average_amount, reverse=True)
    return results


def recurring_budget_lines(
    db: Session,
    month_start: date,
    month_end: date,
    as_of: date | None = None,
) -> list[RecurringBudgetLine]:
    """Recurring series that should reserve money in [month_start, month_end)."""
    today = as_of or date.today()
    lines: list[RecurringBudgetLine] = []
    for series in detect_recurring_series(db, as_of=today):
        if not series.budget_eligible or series.average_amount <= 0:
            continue
        count = _charges_budgeted_in_month(series, month_start, month_end, today)
        if count <= 0:
            continue
        lines.append(RecurringBudgetLine(
            merchant_key=series.merchant_key,
            merchant=series.merchant,
            category=series.category,
            parent_key=series.parent_key,
            cadence=series.cadence,
            expected_amount=round(series.average_amount * count, 2),
        ))
    lines.sort(key=lambda line: line.merchant.lower())
    return lines
