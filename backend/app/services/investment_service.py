"""
Shared investment analytics helpers for the MCP server and API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.analytics_shared import CATEGORY_COLORS
from app.models import Account, BalanceSnapshot, Holding, Item, MarketPrice


def investment_net_equity_total(accounts: list[Account]) -> float:
    """Sum of account balances (net equity after margin)."""
    return sum(float(account.current_balance or 0) for account in accounts)


def account_gross_holdings(holdings: list[Holding]) -> dict[int, float]:
    gross: dict[int, float] = {}
    for holding in holdings:
        gross[holding.account_id] = gross.get(holding.account_id, 0.0) + float(holding.institution_value or 0)
    return gross


def scaled_holding_market_value(
    holding: Holding,
    account: Account,
    gross_by_account: dict[int, float],
) -> float:
    """
    Convert a gross Plaid holding value to net equity share for the account.
    When margin is in use, account.current_balance < sum(holdings); scale down proportionally.
    """
    gross_value = float(holding.institution_value or 0)
    account_gross = gross_by_account.get(holding.account_id, 0.0)
    if account_gross <= 0:
        return gross_value
    net = float(account.current_balance or 0)
    return gross_value * (net / account_gross)


@dataclass(frozen=True)
class InvestmentAllocationSliceData:
    type: str
    value: float
    pct: float
    color: str


@dataclass(frozen=True)
class InvestmentHistoryPointData:
    date: str
    total: float


@dataclass(frozen=True)
class InvestmentPositionData:
    account_name: str
    ticker: str | None
    name: str | None
    type: str | None
    quantity: float
    price: float | None
    value: float
    cost_basis: float | None
    gain: float | None
    gain_pct: float | None
    currency: str | None


@dataclass(frozen=True)
class InvestmentPerformanceData:
    months: int
    total_value: float
    total_cost_basis: float | None
    unrealized_gain: float | None
    account_count: int
    position_count: int
    last_synced_at: str | None
    change_amount: float
    change_pct: float
    allocation: list[InvestmentAllocationSliceData]
    top_positions: list[InvestmentPositionData]
    history: list[InvestmentHistoryPointData]


def build_investment_performance(
    db: Session,
    *,
    months: int = 6,
    top_positions: int = 10,
) -> InvestmentPerformanceData:
    """Return a compact performance-focused view of the investment portfolio."""
    months = max(1, min(int(months), 24))
    top_positions = max(1, min(int(top_positions), 25))

    accounts = _investment_accounts(db)
    account_ids = [account.id for account in accounts]
    accounts_by_id = {account.id: account for account in accounts}

    holdings = (
        db.query(Holding)
        .options(joinedload(Holding.security))
        .filter(Holding.account_id.in_(account_ids))
        .all()
        if account_ids
        else []
    )

    gross_by_account = account_gross_holdings(holdings)
    total_value = investment_net_equity_total(accounts)
    cost_basis_known = [holding for holding in holdings if holding.cost_basis is not None]
    if cost_basis_known:
        total_cost_basis = sum(float(holding.cost_basis) for holding in cost_basis_known)
        value_of_known = sum(
            scaled_holding_market_value(holding, accounts_by_id[holding.account_id], gross_by_account)
            for holding in cost_basis_known
        )
        unrealized_gain = value_of_known - total_cost_basis
    else:
        total_cost_basis = None
        unrealized_gain = None

    by_type: dict[str, float] = {}
    for holding in holdings:
        security_type = (holding.security.type if holding.security else None) or "other"
        net_value = scaled_holding_market_value(holding, accounts_by_id[holding.account_id], gross_by_account)
        by_type[security_type] = by_type.get(security_type, 0.0) + net_value

    allocation = [
        InvestmentAllocationSliceData(
            type=security_type,
            value=round(value, 2),
            pct=round((value / total_value * 100) if total_value else 0.0, 1),
            color=CATEGORY_COLORS[index % len(CATEGORY_COLORS)],
        )
        for index, (security_type, value) in enumerate(sorted(by_type.items(), key=lambda item: -item[1]))
    ]

    top_position_items = []
    sorted_holdings = sorted(
        holdings,
        key=lambda holding: scaled_holding_market_value(
            holding, accounts_by_id[holding.account_id], gross_by_account
        ),
        reverse=True,
    )
    for holding in sorted_holdings[:top_positions]:
        account = accounts_by_id[holding.account_id]
        value = scaled_holding_market_value(holding, account, gross_by_account)
        cost_basis = float(holding.cost_basis) if holding.cost_basis is not None else None
        gain = (value - cost_basis) if cost_basis is not None else None
        gain_pct = (gain / cost_basis * 100) if gain is not None and cost_basis else None
        top_position_items.append(
            InvestmentPositionData(
                account_name=account.name,
                ticker=holding.security.ticker_symbol if holding.security else None,
                name=holding.security.name if holding.security else None,
                type=holding.security.type if holding.security else None,
                quantity=float(holding.quantity),
                price=float(holding.institution_price) if holding.institution_price is not None else None,
                value=round(value, 2),
                cost_basis=round(cost_basis, 2) if cost_basis is not None else None,
                gain=round(gain, 2) if gain is not None else None,
                gain_pct=round(gain_pct, 1) if gain_pct is not None else None,
                currency=holding.iso_currency_code or holding.unofficial_currency_code,
            )
        )

    history = _build_investment_history(db, account_ids=account_ids, months=months, live_total=total_value)
    change_amount, change_pct = _history_change(history)
    last_synced = max((account.item.last_synced_at for account in accounts if account.item.last_synced_at), default=None)

    return InvestmentPerformanceData(
        months=months,
        total_value=round(total_value, 2),
        total_cost_basis=round(total_cost_basis, 2) if total_cost_basis is not None else None,
        unrealized_gain=round(unrealized_gain, 2) if unrealized_gain is not None else None,
        account_count=len(accounts),
        position_count=len(holdings),
        last_synced_at=last_synced.isoformat() if last_synced else None,
        change_amount=change_amount,
        change_pct=change_pct,
        allocation=allocation,
        top_positions=top_position_items,
        history=history,
    )


def _investment_accounts(db: Session) -> list[Account]:
    from app.crypto_tokens import PLAID_SYNC_EXCLUDED_ITEMS

    return (
        db.query(Account)
        .join(Item)
        .filter(
            Item.user_id == 1,
            Item.item_id.notin_(list(PLAID_SYNC_EXCLUDED_ITEMS)),
            Account.type == "investment",
        )
        .all()
    )


def _history_cutoff(months: int) -> date:
    today = date.today()
    months = max(1, min(int(months), 24))
    cutoff_year = today.year - (months // 12)
    cutoff_month = today.month - (months % 12)
    if cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1
    return date(cutoff_year, cutoff_month, 1)


def _snapshot_history(
    db: Session,
    *,
    account_ids: list[int],
    cutoff: date,
) -> list[InvestmentHistoryPointData]:
    rows = (
        db.query(
            BalanceSnapshot.snapshot_date,
            func.sum(BalanceSnapshot.balance).label("total"),
        )
        .filter(
            BalanceSnapshot.account_id.in_(account_ids),
            BalanceSnapshot.snapshot_date >= cutoff,
        )
        .group_by(BalanceSnapshot.snapshot_date)
        .order_by(BalanceSnapshot.snapshot_date.asc())
        .all()
        if account_ids
        else []
    )
    return [
        InvestmentHistoryPointData(
            date=str(row.snapshot_date),
            total=round(float(row.total), 2),
        )
        for row in rows
    ]


def _mark_to_market_history(
    db: Session,
    *,
    account_ids: list[int],
    cutoff: date,
    live_total: float,
) -> list[InvestmentHistoryPointData]:
    """Current-holdings mark-to-market over [cutoff, today].

    Plaid does not provide historical balances, so daily snapshots only exist
    since Ledger first synced. When that span is shorter than the chart
    window, period change would otherwise be identical for 6M and 1Y. Pricing
    today's book against cached MarketPrice rows is the same series the
    optimizer already uses, and it actually covers those windows.
    """
    if not account_ids:
        return []

    holdings = (
        db.query(Holding)
        .options(joinedload(Holding.security))
        .filter(Holding.account_id.in_(account_ids))
        .all()
    )
    if not holdings:
        return []

    accounts_by_id = {
        account.id: account
        for account in db.query(Account).filter(Account.id.in_(account_ids)).all()
    }
    gross_by_account = account_gross_holdings(holdings)

    qty_by_ticker: dict[str, float] = {}
    for holding in holdings:
        security = holding.security
        if not security or not security.ticker_symbol or security.is_cash_equivalent:
            continue
        account = accounts_by_id.get(holding.account_id)
        if account is None:
            continue
        scaled_value = scaled_holding_market_value(holding, account, gross_by_account)
        inst_value = float(holding.institution_value or 0)
        quantity = float(holding.quantity)
        if inst_value > 0 and quantity != 0:
            quantity *= scaled_value / inst_value
        qty_by_ticker[security.ticker_symbol] = qty_by_ticker.get(security.ticker_symbol, 0.0) + quantity

    tickers = [ticker for ticker, qty in qty_by_ticker.items() if qty != 0]
    if not tickers:
        return []

    today = date.today()
    rows = (
        db.query(MarketPrice.ticker, MarketPrice.price_date, MarketPrice.close_price)
        .filter(
            MarketPrice.ticker.in_(tickers),
            MarketPrice.price_date >= cutoff,
            MarketPrice.price_date <= today,
        )
        .order_by(MarketPrice.price_date.asc())
        .all()
    )
    if not rows:
        return []

    by_ticker: dict[str, dict[date, float]] = {ticker: {} for ticker in tickers}
    dates: set[date] = set()
    for ticker, price_date, close_price in rows:
        by_ticker[ticker][price_date] = float(close_price)
        dates.add(price_date)

    last_price: dict[str, float] = {}
    points: list[tuple[date, float]] = []
    for price_date in sorted(dates):
        for ticker in tickers:
            if price_date in by_ticker[ticker]:
                last_price[ticker] = by_ticker[ticker][price_date]
        if not last_price:
            continue
        total = sum(qty_by_ticker[ticker] * last_price[ticker] for ticker in last_price)
        points.append((price_date, total))

    if len(points) < 2:
        return []

    residual = live_total - points[-1][1]
    return [
        InvestmentHistoryPointData(date=str(price_date), total=round(total + residual, 2))
        for price_date, total in points
    ]


def _finalize_history(
    history: list[InvestmentHistoryPointData],
    live_total: float,
) -> list[InvestmentHistoryPointData]:
    today_str = str(date.today())
    live_total = round(live_total, 2)
    if history and history[-1].date == today_str:
        history[-1] = InvestmentHistoryPointData(date=today_str, total=live_total)
    else:
        history.append(InvestmentHistoryPointData(date=today_str, total=live_total))
    return history


def _build_investment_history(
    db: Session,
    *,
    account_ids: list[int],
    months: int,
    live_total: float,
) -> list[InvestmentHistoryPointData]:
    cutoff = _history_cutoff(months)
    history = _snapshot_history(db, account_ids=account_ids, cutoff=cutoff)
    first = date.fromisoformat(history[0].date) if history else None
    # Snapshots shorter than the requested window would make 6M and 1Y report
    # the same period change. Fall back to current-holdings mark-to-market.
    if first is None or first > cutoff:
        marked = _mark_to_market_history(
            db, account_ids=account_ids, cutoff=cutoff, live_total=live_total
        )
        if len(marked) >= 2:
            history = marked
    return _finalize_history(history, live_total)


def _history_change(history: list[InvestmentHistoryPointData]) -> tuple[float, float]:
    if len(history) < 2:
        return 0.0, 0.0

    oldest = history[0].total
    newest = history[-1].total
    change_amount = round(newest - oldest, 2)
    change_pct = round((change_amount / oldest * 100) if oldest > 0 else 0.0, 2)
    return change_amount, change_pct
