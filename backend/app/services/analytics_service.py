"""
Shared analytics helpers for API routes and the MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.analytics_shared import (
    CATEGORY_COLORS,
    category_key_for_income_rules,
    category_key_for_spending_rules,
    display_rollup_category,
    is_excluded_from_income,
    is_excluded_from_spending,
    month_bounds,
)
from app.enrichment import parse_enrichment_json
from app.models import Account, BalanceSnapshot, Item, Transaction
from app.txn_classifier import classify_orm_transaction

LIABILITY_TYPES = frozenset({"credit", "loan"})
EXCLUDED_PLAID_ITEMS = frozenset({"manual_import", "test_item"})
from app.subscriptions import TRAILING_MONTHS, detect_recurring_series


@dataclass(frozen=True)
class CategorySpendItem:
    name: str
    value: float
    color: str
    transaction_count: int


@dataclass(frozen=True)
class RecentTransactionItem:
    id: int
    merchant: str
    account_name: str | None
    date: str
    category: str | None
    amount: float
    initials: str


@dataclass(frozen=True)
class MonthlySummaryData:
    month: str
    total_spending: float
    total_income: float
    savings_rate: float
    spending_by_category: list[CategorySpendItem]
    recent_transactions: list[RecentTransactionItem]
    prev_month_spending: float


@dataclass(frozen=True)
class SpendingByCategoryData:
    start_date: str
    end_date: str
    total_spending: float
    transaction_count: int
    categories: list[CategorySpendItem]


@dataclass(frozen=True)
class TransactionSearchItem:
    id: int
    date: str
    merchant: str
    amount: float
    original_amount: float
    direction: str
    category: str | None
    rollup_category: str
    category_user: str | None
    category_plaid: str | None
    category_plaid_detailed: str | None
    account_name: str | None
    account_type: str | None
    account_subtype: str | None
    payment_channel: str | None
    user_split_pct: float | None
    manual_override: bool
    notes: str | None
    enrichment: dict[str, Any] | None


@dataclass(frozen=True)
class TransactionSearchData:
    total: int
    returned: int
    transactions: list[TransactionSearchItem]


@dataclass(frozen=True)
class CashFlowTxnItem:
    merchant: str
    amount: float
    date: str


@dataclass(frozen=True)
class CashFlowNodeItem:
    id: str
    label: str
    amount: float
    color: str
    top_transactions: list[CashFlowTxnItem]


@dataclass(frozen=True)
class CashFlowData:
    month: str
    total_income: float
    total_spending: float
    savings: float
    income_sources: list[CashFlowNodeItem]
    spending_categories: list[CashFlowNodeItem]


@dataclass(frozen=True)
class RecurringSpendItem:
    merchant: str
    category: str
    cadence: str
    average_amount: float
    last_date: str
    next_expected_date: str
    occurrence_count: int


@dataclass(frozen=True)
class RecurringSpendData:
    months: int
    subscriptions: list[RecurringSpendItem]


@dataclass(frozen=True)
class BudgetVsActualItem:
    id: int
    category: str
    limit: float
    spent: float
    remaining: float
    percent_used: float
    over_budget: bool
    color: str
    virtual: bool = False


@dataclass(frozen=True)
class BudgetVsActualData:
    month: str
    budgets: list[BudgetVsActualItem]
    total_limit: float
    total_spent: float
    total_remaining: float


@dataclass(frozen=True)
class TrendMonthItem:
    month_key: str          # "2026-01"
    label: str              # "Jan"
    full_label: str         # "Jan 2026"
    total_spending: float
    total_income: float
    net: float              # income - spending
    is_partial: bool        # True for the in-progress current month


@dataclass(frozen=True)
class TrendCategoryItem:
    name: str
    color: str
    monthly: list[float]    # spend per month, aligned with TrendsData.months
    total: float            # over the whole window (incl. partial month)
    monthly_avg: float      # over complete months only
    share_pct: float        # of window spending
    last_full: float        # spend in the most recent complete month
    prior_avg: float        # avg of complete months before the last full one
    change_vs_prior_pct: float | None  # last_full vs prior_avg; None if no base


@dataclass(frozen=True)
class TrendsData:
    months: list[TrendMonthItem]
    categories: list[TrendCategoryItem]          # all categories, by total desc
    period_spending: float                       # window total (incl. partial month)
    period_income: float
    monthly_avg_spending: float                  # complete months in window
    prev_monthly_avg_spending: float             # same-length window before this one
    spending_change_pct: float | None            # between the two averages


@dataclass(frozen=True)
class NetWorthSnapshotItem:
    date: str
    total: float


@dataclass(frozen=True)
class AccountBreakdownItem:
    id: int
    name: str
    type: str
    subtype: str | None
    balance: float
    is_liability: bool


@dataclass(frozen=True)
class NetWorthData:
    current_net_worth: float
    total_assets: float
    total_liabilities: float
    accounts: list[AccountBreakdownItem]
    snapshots: list[NetWorthSnapshotItem]
    change_amount: float
    change_pct: float


def build_net_worth(db: Session, months: int = 6) -> NetWorthData:
    """Historical net worth from daily balance snapshots."""
    accounts = (
        db.query(Account)
        .join(Item, Account.item_id == Item.id)
        .filter(Item.item_id.notin_(list(EXCLUDED_PLAID_ITEMS)))
        .all()
    )

    total_assets = sum(float(a.current_balance or 0) for a in accounts if a.type not in LIABILITY_TYPES)
    total_liabilities = sum(float(a.current_balance or 0) for a in accounts if a.type in LIABILITY_TYPES)
    live_total = round(total_assets - total_liabilities, 2)

    account_breakdowns = [
        AccountBreakdownItem(
            id=a.id,
            name=a.name,
            type=a.type,
            subtype=a.subtype,
            balance=round(float(a.current_balance or 0), 2),
            is_liability=a.type in LIABILITY_TYPES,
        )
        for a in sorted(accounts, key=lambda a: (a.type in LIABILITY_TYPES, -float(a.current_balance or 0)))
    ]

    today_d = date.today()
    cutoff_year = today_d.year - (months // 12)
    cutoff_month = today_d.month - (months % 12)
    if cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1
    cutoff = date(cutoff_year, cutoff_month, 1)

    signed_bal = case(
        (Account.type.in_(list(LIABILITY_TYPES)), -BalanceSnapshot.balance),
        else_=BalanceSnapshot.balance,
    )
    rows = (
        db.query(
            BalanceSnapshot.snapshot_date,
            func.sum(signed_bal).label("total"),
        )
        .join(Account, BalanceSnapshot.account_id == Account.id)
        .join(Item, Account.item_id == Item.id)
        .filter(
            Item.item_id.notin_(list(EXCLUDED_PLAID_ITEMS)),
            BalanceSnapshot.snapshot_date >= cutoff,
        )
        .group_by(BalanceSnapshot.snapshot_date)
        .order_by(BalanceSnapshot.snapshot_date.asc())
        .all()
    )

    snapshots = [
        NetWorthSnapshotItem(date=str(row.snapshot_date), total=round(float(row.total), 2))
        for row in rows
    ]

    today_str = str(today_d)
    if snapshots and snapshots[-1].date == today_str:
        snapshots[-1] = NetWorthSnapshotItem(date=today_str, total=live_total)
    else:
        snapshots.append(NetWorthSnapshotItem(date=today_str, total=live_total))

    if len(snapshots) >= 2:
        oldest = snapshots[0].total
        newest = snapshots[-1].total
        change_amount = round(newest - oldest, 2)
        change_pct = round((change_amount / oldest * 100) if oldest > 0 else 0.0, 2)
    else:
        change_amount = 0.0
        change_pct = 0.0

    return NetWorthData(
        current_net_worth=live_total,
        total_assets=round(total_assets, 2),
        total_liabilities=round(total_liabilities, 2),
        accounts=account_breakdowns,
        snapshots=snapshots,
        change_amount=change_amount,
        change_pct=change_pct,
    )


def resolve_month_window(month: str | None) -> tuple[int, int, date, date, str]:
    """Parse a YYYY-MM string into a calendar month window."""
    if month:
        try:
            anchor = date.fromisoformat(f"{month}-01")
        except ValueError as exc:
            raise ValueError("month must be in YYYY-MM format") from exc
    else:
        anchor = date.today()

    start, end = month_bounds(anchor.year, anchor.month)
    return anchor.year, anchor.month, start, end, f"{anchor.year:04d}-{anchor.month:02d}"


def build_monthly_summary(db: Session, month: str | None = None) -> MonthlySummaryData:
    """Return the monthly spending summary used by both the API and MCP."""
    year, mon, start, end, month_key = resolve_month_window(month)
    prev_year, prev_mon = (year - 1, 12) if mon == 1 else (year, mon - 1)
    prev_start, prev_end = month_bounds(prev_year, prev_mon)

    current_rows = _fetch_transaction_rows(db, start=start, end=end)
    previous_rows = _fetch_transaction_rows(db, start=prev_start, end=prev_end)

    spending_by_category, total_spending, _ = _aggregate_spending(current_rows)
    prev_month_spending = _aggregate_spending(previous_rows)[1]
    total_income = _aggregate_income(current_rows)
    savings_rate = ((total_income - total_spending) / total_income * 100) if total_income > 0 else 0.0

    recent_transactions = [
        RecentTransactionItem(
            id=txn.id,
            merchant=txn.merchant or "",
            account_name=account_name,
            date=_format_recent_date(txn.date),
            category=txn.display_category,
            amount=round(_effective_amount(txn), 2),
            initials=_merchant_initials(txn),
        )
        for txn, account_name, _, _ in current_rows[:8]
    ]

    return MonthlySummaryData(
        month=month_key,
        total_spending=round(total_spending, 2),
        total_income=round(total_income, 2),
        savings_rate=round(savings_rate, 1),
        spending_by_category=spending_by_category,
        recent_transactions=recent_transactions,
        prev_month_spending=round(prev_month_spending, 2),
    )


def get_spending_by_category(
    db: Session,
    start_date: date,
    end_date: date,
    top_n: int | None = None,
) -> SpendingByCategoryData:
    """Aggregate spending by category for an inclusive date range."""
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    rows = _fetch_transaction_rows(
        db,
        start=start_date,
        end=_inclusive_end_to_exclusive(end_date),
    )
    categories, total_spending, transaction_count = _aggregate_spending(rows, top_n=top_n)

    return SpendingByCategoryData(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        total_spending=round(total_spending, 2),
        transaction_count=transaction_count,
        categories=categories,
    )


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def build_trends(db: Session, months: int = 6) -> TrendsData:
    """
    Multi-month spending/income trends. Fetches one window of 2×months so the
    prior same-length window is available for period-over-period comparison.

    The current month is flagged is_partial and excluded from all averages —
    otherwise every trend would appear to dip at the end of the chart.
    """
    today = date.today()

    # Month keys for the visible window, oldest → current
    window: list[tuple[int, int]] = [
        _shift_month(today.year, today.month, -i) for i in range(months - 1, -1, -1)
    ]
    fetch_start = date(*_shift_month(today.year, today.month, -(2 * months - 1)), 1)
    _, window_end = month_bounds(today.year, today.month)
    rows = _fetch_transaction_rows(db, start=fetch_start, end=window_end)

    # (month_key → category → spend) and (month_key → income) over the full fetch
    spend_by_month: dict[str, dict[str, float]] = {}
    income_by_month: dict[str, float] = {}
    for txn, _, _, _ in rows:
        mk = f"{txn.date.year:04d}-{txn.date.month:02d}"
        amount = float(txn.amount)
        if amount > 0:
            if is_excluded_from_spending(_spending_category_key(txn)):
                continue
            category = _rollup_category(txn, "Uncategorized")
            bucket = spend_by_month.setdefault(mk, {})
            bucket[category] = bucket.get(category, 0.0) + _effective_amount(txn)
        elif amount < 0:
            category = _income_category_key(txn)
            if is_excluded_from_income(category):
                continue
            income_by_month[mk] = income_by_month.get(mk, 0.0) + abs(amount)

    current_key = f"{today.year:04d}-{today.month:02d}"

    # Months before the first transaction ever seen aren't "months you spent
    # $0" — they're months with no data. Drop them from the window and from
    # every average, or young accounts show huge phantom "increases".
    data_keys = set(spend_by_month) | set(income_by_month)
    data_start = min(data_keys) if data_keys else None

    window = [
        (y, m) for y, m in window
        if data_start is None or f"{y:04d}-{m:02d}" >= data_start
    ] or window[-1:]
    window_keys = [f"{y:04d}-{m:02d}" for y, m in window]
    complete_keys = [k for k in window_keys if k != current_key]

    month_items = []
    for (year, mon), key in zip(window, window_keys):
        start = date(year, mon, 1)
        spending = sum(spend_by_month.get(key, {}).values())
        income = income_by_month.get(key, 0.0)
        month_items.append(TrendMonthItem(
            month_key=key,
            label=start.strftime("%b"),
            full_label=start.strftime("%b %Y"),
            total_spending=round(spending, 2),
            total_income=round(income, 2),
            net=round(income - spending, 2),
            is_partial=key == current_key,
        ))

    # Per-category series over the visible window
    category_totals: dict[str, float] = {}
    for key in window_keys:
        for category, amount in spend_by_month.get(key, {}).items():
            category_totals[category] = category_totals.get(category, 0.0) + amount
    period_spending = sum(category_totals.values())

    last_full_key = complete_keys[-1] if complete_keys else None
    prior_keys = complete_keys[:-1]

    categories = []
    ordered = sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
    for index, (name, total) in enumerate(ordered):
        monthly = [round(spend_by_month.get(key, {}).get(name, 0.0), 2) for key in window_keys]
        complete_values = [spend_by_month.get(key, {}).get(name, 0.0) for key in complete_keys]
        monthly_avg = sum(complete_values) / len(complete_values) if complete_values else 0.0
        last_full = spend_by_month.get(last_full_key, {}).get(name, 0.0) if last_full_key else 0.0
        prior_values = [spend_by_month.get(key, {}).get(name, 0.0) for key in prior_keys]
        prior_avg = sum(prior_values) / len(prior_values) if prior_values else 0.0
        change = ((last_full - prior_avg) / prior_avg * 100) if prior_avg > 0 else None
        categories.append(TrendCategoryItem(
            name=name,
            color=CATEGORY_COLORS[index % len(CATEGORY_COLORS)],
            monthly=monthly,
            total=round(total, 2),
            monthly_avg=round(monthly_avg, 2),
            share_pct=round(total / period_spending * 100, 1) if period_spending > 0 else 0.0,
            last_full=round(last_full, 2),
            prior_avg=round(prior_avg, 2),
            change_vs_prior_pct=round(change, 1) if change is not None else None,
        ))

    period_income = sum(income_by_month.get(key, 0.0) for key in window_keys)
    monthly_avg_spending = (
        sum(sum(spend_by_month.get(key, {}).values()) for key in complete_keys) / len(complete_keys)
        if complete_keys else 0.0
    )

    # Prior same-length window (all complete months), for the headline
    # comparison. Months with no data yet are excluded the same way.
    prev_window_keys = [
        key
        for y, m in (_shift_month(today.year, today.month, -i) for i in range(2 * months - 1, months - 1, -1))
        if (key := f"{y:04d}-{m:02d}") not in window_keys
        and (data_start is None or key >= data_start)
    ]
    prev_monthly_avg = (
        sum(sum(spend_by_month.get(key, {}).values()) for key in prev_window_keys) / len(prev_window_keys)
        if prev_window_keys else 0.0
    )
    spending_change_pct = (
        round((monthly_avg_spending - prev_monthly_avg) / prev_monthly_avg * 100, 1)
        if prev_monthly_avg > 0 else None
    )

    return TrendsData(
        months=month_items,
        categories=categories,
        period_spending=round(period_spending, 2),
        period_income=round(period_income, 2),
        monthly_avg_spending=round(monthly_avg_spending, 2),
        prev_monthly_avg_spending=round(prev_monthly_avg, 2),
        spending_change_pct=spending_change_pct,
    )


def build_cash_flow(db: Session, month: str | None = None) -> CashFlowData:
    """Return the monthly income/spending buckets used by the spending view."""
    _, _, start, end, month_key = resolve_month_window(month)

    month_txns = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .filter(
            Transaction.removed.is_(False),
            # Pending transactions ARE counted so purchases show up immediately.
            # Plaid links a pending txn to its posted version and marks the
            # pending one `removed` on the next sync, so this doesn't double-count.
            Transaction.hidden.is_(False),
            Transaction.date >= start,
            Transaction.date < end,
        )
        .all()
    )

    income_pool: list[Transaction] = []
    spend_pool: list[Transaction] = []
    investment_pool: list[Transaction] = []

    for txn in month_txns:
        role = classify_orm_transaction(txn)
        if role == "income":
            income_pool.append(txn)
        elif role == "spending":
            spend_pool.append(txn)
        elif role == "investments":
            investment_pool.append(txn)
        # transfer / exclude → omitted from cash-flow sinks

    income_buckets: dict[str, float] = {}
    for txn in income_pool:
        category = _display_rollup_category(txn, "Other Income")
        income_buckets[category] = income_buckets.get(category, 0.0) + abs(float(txn.amount))

    spend_buckets: dict[str, float] = {}
    for txn in spend_pool:
        category = _display_rollup_category(txn, "Uncategorized")
        spend_buckets[category] = spend_buckets.get(category, 0.0) + _effective_amount(txn)

    investment_total = round(sum(_effective_amount(txn) for txn in investment_pool), 2)
    if investment_total > 0:
        spend_buckets["Investments"] = spend_buckets.get("Investments", 0.0) + investment_total

    income_sources = [
        CashFlowNodeItem(
            id=category,
            label=category,
            amount=round(total, 2),
            color=_income_colors()[index % len(_income_colors())],
            top_transactions=_top_income_txns(income_pool, category),
        )
        for index, (category, total) in enumerate(
            sorted(income_buckets.items(), key=lambda item: item[1], reverse=True)
        )
    ]
    spending_categories = [
        CashFlowNodeItem(
            id=category,
            label=category,
            amount=round(total, 2),
            color=CATEGORY_COLORS[index % len(CATEGORY_COLORS)],
            top_transactions=(
                _top_investment_txns(investment_pool)
                if category == "Investments"
                else _top_spending_txns(spend_pool, category)
            ),
        )
        for index, (category, total) in enumerate(
            sorted(spend_buckets.items(), key=lambda item: item[1], reverse=True)
        )
    ]

    total_income = round(sum(item.amount for item in income_sources), 2)
    total_spending = round(sum(item.amount for item in spending_categories), 2)
    return CashFlowData(
        month=month_key,
        total_income=total_income,
        total_spending=total_spending,
        savings=max(round(total_income - total_spending, 2), 0.0),
        income_sources=income_sources,
        spending_categories=spending_categories,
    )


def build_recurring_spend(db: Session, months: int = TRAILING_MONTHS) -> RecurringSpendData:
    """Return recurring-spend series detected from transaction history."""
    months = _bounded_limit(months, default=TRAILING_MONTHS, maximum=24)
    results = detect_recurring_series(db, months=months)
    return RecurringSpendData(
        months=months,
        subscriptions=[
            RecurringSpendItem(
                merchant=item.merchant,
                category=item.category,
                cadence=item.cadence,
                average_amount=item.average_amount,
                last_date=item.last_date.isoformat(),
                next_expected_date=item.next_expected_date.isoformat(),
                occurrence_count=item.occurrence_count,
            )
            for item in results
        ],
    )


def build_budget_vs_actual(ldb: Session, bdb: Session, month: str | None = None) -> BudgetVsActualData:
    """Return budget limits and actual spending for the requested month."""
    _, _, _, _, month_key = resolve_month_window(month)

    from app.routes.budgets import get_budget_items

    items = get_budget_items(bdb, ldb, month_key)
    budgets = [
        BudgetVsActualItem(
            id=item.id,
            category=item.category,
            limit=round(item.limit, 2),
            spent=round(item.spent, 2),
            remaining=round(item.limit - item.spent, 2),
            percent_used=round((item.spent / item.limit * 100) if item.limit > 0 else 0.0, 1),
            over_budget=(not item.virtual) and item.spent > item.limit,
            color=item.color,
            virtual=item.virtual,
        )
        for item in items
    ]
    total_limit = round(sum(item.limit for item in budgets if not item.virtual), 2)
    total_spent = round(sum(item.spent for item in budgets), 2)
    return BudgetVsActualData(
        month=month_key,
        budgets=budgets,
        total_limit=total_limit,
        total_spent=total_spent,
        total_remaining=round(total_limit - total_spent, 2),
    )


def search_transactions(
    db: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    merchant: str | None = None,
    category: str | None = None,
    account: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = 25,
) -> TransactionSearchData:
    """
    Search transaction rows using read-oriented defaults.

    `min_amount` and `max_amount` apply to the absolute effective amount so
    the same filter works for both income and spending.
    """
    if start_date and end_date and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    limit = _bounded_limit(limit, default=25, maximum=100)

    query = (
        db.query(
            Transaction,
            Account.name.label("account_name"),
            Account.type.label("account_type"),
            Account.subtype.label("account_subtype"),
        )
        .outerjoin(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.removed.is_(False),
            Transaction.hidden.is_(False),
        )
    )

    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if merchant:
        merchant_term = f"%{merchant.strip().lower()}%"
        query = query.filter(func.lower(Transaction.merchant).like(merchant_term))
    if account:
        account_term = f"%{account.strip().lower()}%"
        query = query.filter(func.lower(func.coalesce(Account.name, "")).like(account_term))

    rows = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()

    category_filter = category.strip().lower() if category else None
    filtered_rows = [
        row
        for row in rows
        if _matches_filters(
            row[0],
            category_filter=category_filter,
            min_amount=min_amount,
            max_amount=max_amount,
        )
    ]

    transactions = [
        TransactionSearchItem(
            id=txn.id,
            date=txn.date.isoformat(),
            merchant=txn.merchant or "",
            amount=round(_effective_amount(txn), 2),
            original_amount=round(float(txn.amount), 2),
            direction="income" if float(txn.amount) < 0 else "spending",
            category=txn.display_category,
            rollup_category=_rollup_category(txn, "Uncategorized"),
            category_user=txn.category_user,
            category_plaid=txn.category_plaid,
            category_plaid_detailed=txn.category_plaid_detailed,
            account_name=account_name,
            account_type=account_type,
            account_subtype=account_subtype,
            payment_channel=txn.payment_channel,
            user_split_pct=float(txn.user_split_pct) if txn.user_split_pct is not None else None,
            manual_override=bool(txn.manual_override),
            notes=txn.notes,
            enrichment=parse_enrichment_json(txn.enrichment_json),
        )
        for txn, account_name, account_type, account_subtype in filtered_rows[:limit]
    ]

    return TransactionSearchData(
        total=len(filtered_rows),
        returned=len(transactions),
        transactions=transactions,
    )


def _fetch_transaction_rows(
    db: Session,
    *,
    start: date,
    end: date,
) -> list[tuple[Transaction, str | None, str | None, str | None]]:
    return (
        db.query(
            Transaction,
            Account.name.label("account_name"),
            Account.type.label("account_type"),
            Account.subtype.label("account_subtype"),
        )
        .outerjoin(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.removed.is_(False),
            # Pending transactions ARE counted so purchases show up immediately.
            # Plaid links a pending txn to its posted version and marks the
            # pending one `removed` on the next sync, so this doesn't double-count.
            Transaction.hidden.is_(False),
            Transaction.date >= start,
            Transaction.date < end,
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )


def _aggregate_spending(
    rows: list[tuple[Transaction, str | None, str | None, str | None]],
    top_n: int | None = None,
) -> tuple[list[CategorySpendItem], float, int]:
    buckets: dict[str, dict[str, float | int]] = {}
    transaction_count = 0

    for txn, _, _, _ in rows:
        if float(txn.amount) <= 0:
            continue

        if is_excluded_from_spending(_spending_category_key(txn)):
            continue
        category = _rollup_category(txn, "Uncategorized")

        bucket = buckets.setdefault(category, {"value": 0.0, "transaction_count": 0})
        bucket["value"] += _effective_amount(txn)
        bucket["transaction_count"] += 1
        transaction_count += 1

    ordered = sorted(
        buckets.items(),
        key=lambda item: float(item[1]["value"]),
        reverse=True,
    )
    total_spending = round(
        sum(float(values["value"]) for _, values in ordered),
        2,
    )

    if top_n is not None:
        ordered = ordered[: _bounded_limit(top_n, default=10, maximum=50)]

    categories = [
        CategorySpendItem(
            name=name,
            value=round(float(values["value"]), 2),
            color=CATEGORY_COLORS[index % len(CATEGORY_COLORS)],
            transaction_count=int(values["transaction_count"]),
        )
        for index, (name, values) in enumerate(ordered)
    ]
    return categories, total_spending, transaction_count


def _aggregate_income(rows: list[tuple[Transaction, str | None, str | None, str | None]]) -> float:
    total_income = 0.0
    for txn, _, _, _ in rows:
        if float(txn.amount) >= 0:
            continue

        if is_excluded_from_income(_income_category_key(txn)):
            continue

        total_income += abs(float(txn.amount))

    return round(total_income, 2)


def _matches_filters(
    txn: Transaction,
    *,
    category_filter: str | None,
    min_amount: float | None,
    max_amount: float | None,
) -> bool:
    if category_filter and not _category_matches(txn, category_filter):
        return False

    effective_amount = abs(_effective_amount(txn))
    if min_amount is not None and effective_amount < min_amount:
        return False
    if max_amount is not None and effective_amount > max_amount:
        return False

    return True


def _category_matches(txn: Transaction, needle: str) -> bool:
    haystacks = [
        txn.category_user,
        txn.category_plaid,
        txn.category_plaid_detailed,
        txn.display_category,
        _rollup_category(txn, "Uncategorized"),
    ]
    return any(needle in value.lower() for value in haystacks if value)


def _rollup_category(txn: Transaction, default: str) -> str:
    return txn.rollup_category or default


def _display_rollup_category(txn: Transaction, default: str) -> str:
    return display_rollup_category(
        txn.category_user, txn.category_plaid, txn.category_plaid_detailed, default
    )


def _income_category_key(txn: Transaction) -> str:
    return category_key_for_income_rules(
        txn.category_user,
        txn.category_plaid,
        txn.category_plaid_detailed,
    )


def _spending_category_key(txn: Transaction) -> str:
    return category_key_for_spending_rules(
        txn.category_user,
        txn.category_plaid,
        txn.category_plaid_detailed,
    )


def _effective_amount(txn: Transaction) -> float:
    return float(txn.amount) * float(txn.user_split_pct or 1)


def _top_income_txns(pool: list[Transaction], category: str, limit: int = 3) -> list[CashFlowTxnItem]:
    matching = [txn for txn in pool if _display_rollup_category(txn, "Other Income") == category]
    matching.sort(key=lambda txn: abs(float(txn.amount)), reverse=True)
    return [
        CashFlowTxnItem(
            merchant=txn.merchant or "",
            amount=round(abs(float(txn.amount)), 2),
            date=txn.date.isoformat(),
        )
        for txn in matching[:limit]
    ]


def _top_spending_txns(pool: list[Transaction], category: str, limit: int = 3) -> list[CashFlowTxnItem]:
    matching = [txn for txn in pool if _display_rollup_category(txn, "Uncategorized") == category]
    matching.sort(key=_effective_amount, reverse=True)
    return [
        CashFlowTxnItem(
            merchant=txn.merchant or "",
            amount=round(_effective_amount(txn), 2),
            date=txn.date.isoformat(),
        )
        for txn in matching[:limit]
    ]


def _top_investment_txns(pool: list[Transaction], limit: int = 3) -> list[CashFlowTxnItem]:
    matching = sorted(pool, key=_effective_amount, reverse=True)
    return [
        CashFlowTxnItem(
            merchant=txn.merchant or "",
            amount=round(_effective_amount(txn), 2),
            date=txn.date.isoformat(),
        )
        for txn in matching[:limit]
    ]


def _income_colors() -> list[str]:
    return ["#4ec38a", "#7fb0ff", "#8a7df0", "#4fc4c4", "#a8d8a8"]


def _merchant_initials(txn: Transaction) -> str:
    words = (txn.merchant or "").split()
    if float(txn.amount) < 0:
        return "+"
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if words:
        return words[0][:2].upper()
    return "??"


def _format_recent_date(txn_date: date) -> str:
    today = date.today()
    if txn_date == today:
        return "Today"
    if txn_date.year == today.year:
        return txn_date.strftime("%b") + " " + str(txn_date.day)
    return txn_date.strftime("%b") + " " + str(txn_date.day) + f", {txn_date.year}"


def _inclusive_end_to_exclusive(end_date: date) -> date:
    return end_date.fromordinal(end_date.toordinal() + 1)


def _bounded_limit(value: int | None, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    return max(1, min(int(value), maximum))
