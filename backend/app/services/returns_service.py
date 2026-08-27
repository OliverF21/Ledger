# backend/app/services/returns_service.py
"""
Cash-flow-aware portfolio return calculations. Raw balance deltas overstate or
understate performance whenever money moves in/out (a deposit reads as a fake
gain, a withdrawal as a fake loss). Time-weighted return (TWR) isolates
investment-selection performance from the user's deposit/withdrawal timing;
money-weighted return (XIRR) is "what the user actually earned," sensitive to
that timing. risk_service.py (Task 7) uses the TWR series for
volatility/Sharpe/VaR/drawdown/beta; the /investments/risk/metrics endpoint
(Task 8) surfaces both TWR and XIRR side by side.

IMPORTANT: this assumes Plaid's InvestmentTransaction.amount sign convention
for type == "cash" mirrors buy/sell (positive = cash leaving the brokerage, so
a deposit is negative). Verify this against real data before trusting the
output — see the plan doc, Task 6 Step 1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scipy.optimize import brentq
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import BalanceSnapshot, InvestmentTransaction

EXTERNAL_CASH_FLOW_TYPES = ("cash", "transfer")

# Plaid's investment_transaction_type is a coarse enum: dividends, interest,
# and capital-gain distributions all share type == "cash" with deposits and
# withdrawals, distinguished only by `subtype`. Only these subtypes represent
# money genuinely crossing the brokerage boundary (external to the account);
# everything else with type in EXTERNAL_CASH_FLOW_TYPES (dividend, interest,
# qualified dividend, long-term/short-term capital gain, etc.) is investment
# income already reflected in the balance and must stay out of TWR/XIRR flows.
EXTERNAL_CASH_FLOW_SUBTYPES = {
    "deposit", "withdrawal", "contribution", "distribution", "transfer", "send", "request",
}


@dataclass(frozen=True)
class TWRPoint:
    date: date
    growth_index: float  # growth of $1 invested at the start of the series


@dataclass(frozen=True)
class CashFlow:
    date: date
    amount: float  # positive = money in (deposit), negative = money out (withdrawal)


def _daily_totals(db: Session, account_ids: list[int], start: date, end: date) -> dict[date, float]:
    if not account_ids:
        return {}
    rows = (
        db.query(BalanceSnapshot.snapshot_date, func.sum(BalanceSnapshot.balance).label("total"))
        .filter(
            BalanceSnapshot.account_id.in_(account_ids),
            BalanceSnapshot.snapshot_date >= start,
            BalanceSnapshot.snapshot_date <= end,
        )
        .group_by(BalanceSnapshot.snapshot_date)
        .order_by(BalanceSnapshot.snapshot_date.asc())
        .all()
    )
    return {row.snapshot_date: float(row.total) for row in rows}


def external_cash_flows(db: Session, account_ids: list[int], start: date, end: date) -> list[CashFlow]:
    """External deposits/withdrawals between the brokerage and outside accounts
    — the flows a TWR calculation must exclude and an XIRR calculation must use
    as its dated cashflows. Internal buys/sells/dividends are already reflected
    in the account's balance and must NOT be treated as external flows."""
    if not account_ids:
        return []
    rows = (
        db.query(InvestmentTransaction)
        .filter(
            InvestmentTransaction.account_id.in_(account_ids),
            InvestmentTransaction.type.in_(EXTERNAL_CASH_FLOW_TYPES),
            InvestmentTransaction.date >= start,
            InvestmentTransaction.date <= end,
        )
        .order_by(InvestmentTransaction.date.asc())
        .all()
    )
    return [
        CashFlow(date=t.date, amount=-float(t.amount))
        for t in rows
        if (t.subtype or "").strip().lower() in EXTERNAL_CASH_FLOW_SUBTYPES
    ]


def build_twr_series(db: Session, account_ids: list[int], start: date, end: date) -> list[TWRPoint]:
    """
    Time-weighted return as a growth-of-$1 index. Breaks the timeline into
    sub-periods at each external cash-flow date (using the daily BalanceSnapshot
    totals as the only available valuation points — there's no per-security
    daily history, so this is portfolio-level, not per-holding), links
    sub-period returns geometrically (Modified-Dietz style: a same-day flow is
    excluded from that day's return since it didn't have time to earn one).
    """
    totals = _daily_totals(db, account_ids, start, end)
    if not totals:
        return []

    dates = sorted(totals.keys())
    flows_by_date: dict[date, float] = {}
    for flow in external_cash_flows(db, account_ids, start, end):
        flows_by_date[flow.date] = flows_by_date.get(flow.date, 0.0) + flow.amount

    series: list[TWRPoint] = [TWRPoint(date=dates[0], growth_index=1.0)]
    growth = 1.0
    prev_value = totals[dates[0]]

    for d in dates[1:]:
        value = totals[d]
        flow = flows_by_date.get(d, 0.0)
        if prev_value > 0:
            period_return = (value - flow - prev_value) / prev_value
            growth *= (1 + period_return)
        series.append(TWRPoint(date=d, growth_index=growth))
        prev_value = value

    return series


def build_cagr(series: list[TWRPoint]) -> float | None:
    """Annualized return of a TWR growth-index series, as a percentage."""
    if len(series) < 2:
        return None
    days = (series[-1].date - series[0].date).days
    if days <= 0 or series[0].growth_index <= 0:
        return None
    total_growth = series[-1].growth_index / series[0].growth_index
    if total_growth <= 0:
        return None
    return (total_growth ** (365.0 / days) - 1) * 100


def build_mwr_xirr(db: Session, account_ids: list[int], start: date, end: date) -> float | None:
    """
    Money-weighted return (XIRR): the discount rate that zeroes the NPV of the
    starting balance (as an outflow), every external cash flow in between, and
    the ending balance (as an inflow). Unlike TWR, this IS sensitive to when
    the user deposited/withdrew — "what did the user's money actually earn,"
    not "how did the strategy perform."
    """
    totals = _daily_totals(db, account_ids, start, end)
    if not totals:
        return None
    dates = sorted(totals.keys())
    start_value = totals[dates[0]]
    end_value = totals[dates[-1]]

    flows = external_cash_flows(db, account_ids, start, end)
    dated_flows = [CashFlow(date=dates[0], amount=-start_value)]
    # external_cash_flows() reports portfolio-perspective signs (positive =
    # money in). XIRR's NPV needs investor-perspective signs (negative = money
    # the investor put in, i.e. an outflow) to match start_value/end_value
    # below, so flip them here.
    # Include flows on the last snapshot date (`<= dates[-1]`): that day's
    # ending balance already embeds the deposit/withdrawal, so dropping the
    # flow would treat new cash as a gain (or a withdrawal as a loss). Flows
    # on the first snapshot date stay out — start_value is an end-of-day
    # total and already includes them.
    dated_flows += [
        CashFlow(date=f.date, amount=-f.amount)
        for f in flows
        if dates[0] < f.date <= dates[-1]
    ]
    dated_flows.append(CashFlow(date=dates[-1], amount=end_value))

    if all(f.amount <= 0 for f in dated_flows) or all(f.amount >= 0 for f in dated_flows):
        return None  # no sign change - XIRR undefined (e.g. zero balance throughout)

    def npv(rate: float) -> float:
        return sum(
            f.amount / ((1 + rate) ** ((f.date - dates[0]).days / 365.0))
            for f in dated_flows
        )

    try:
        return brentq(npv, -0.99, 10.0) * 100
    except ValueError:
        return None
