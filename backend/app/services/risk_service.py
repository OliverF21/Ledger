# backend/app/services/risk_service.py
"""
Portfolio risk & performance metrics: volatility, Sharpe ratio, historical VaR,
max drawdown, and beta vs. SPY — computed from the TWR growth-of-$1 series
(app.services.returns_service) so cash flows don't distort them, plus the
cached risk-free rate (app.risk_free_rate) and SPY daily closes (MarketPrice).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.models import MarketPrice
from app.risk_free_rate import get_cached_risk_free_rate
from app.services.investment_service import _investment_accounts
from app.services.returns_service import TWRPoint, build_cagr, build_mwr_xirr, build_twr_series

# Portfolio value is observable every day the sync runs regardless of which
# market is open (equities close weekends, crypto doesn't) — 365 rather than
# the equity-only 252-trading-day convention keeps the annualization consistent
# for a mixed stock+crypto book. See plan doc §"Metrics" research notes.
TRADING_DAYS_PER_YEAR = 365
BENCHMARK_TICKER = "SPY"
MIN_DATA_POINTS = 5


@dataclass(frozen=True)
class RiskMetricsData:
    lookback_days: int
    as_of: str
    volatility_pct: float | None
    sharpe_ratio: float | None
    var_95_pct: float | None
    var_99_pct: float | None
    max_drawdown_pct: float | None
    drawdown_duration_days: int | None
    beta_vs_spy: float | None
    cagr_pct: float | None
    twr_pct: float | None
    mwr_pct: float | None
    risk_free_rate_pct: float
    data_points: int


def _daily_returns(growth_index: list[float]) -> np.ndarray:
    arr = np.array(growth_index, dtype=float)
    if len(arr) < 2:
        return np.array([])
    return arr[1:] / arr[:-1] - 1


def _max_drawdown(growth_index: list[float]) -> tuple[float | None, int | None]:
    if len(growth_index) < 2:
        return None, None
    arr = np.array(growth_index, dtype=float)
    running_max = np.maximum.accumulate(arr)
    drawdowns = (arr - running_max) / running_max
    max_dd = float(drawdowns.min())

    trough_idx = int(drawdowns.argmin())
    peak_idx = int(np.argmax(arr[: trough_idx + 1]))
    duration = trough_idx - peak_idx
    return max_dd * 100, duration


def _compute_beta(db: Session, twr_series: list[TWRPoint]) -> float | None:
    if len(twr_series) < MIN_DATA_POINTS:
        return None
    dates = [p.date for p in twr_series]
    spy_rows = (
        db.query(MarketPrice.price_date, MarketPrice.close_price)
        .filter(MarketPrice.ticker == BENCHMARK_TICKER, MarketPrice.price_date.in_(dates))
        .order_by(MarketPrice.price_date.asc())
        .all()
    )
    spy_by_date = {row.price_date: float(row.close_price) for row in spy_rows}
    common_dates = [d for d in dates if d in spy_by_date]
    if len(common_dates) < MIN_DATA_POINTS:
        return None

    portfolio_by_date = {p.date: p.growth_index for p in twr_series}
    port_values = np.array([portfolio_by_date[d] for d in common_dates], dtype=float)
    spy_values = np.array([spy_by_date[d] for d in common_dates], dtype=float)

    port_returns = port_values[1:] / port_values[:-1] - 1
    spy_returns = spy_values[1:] / spy_values[:-1] - 1
    if len(spy_returns) < 2 or np.var(spy_returns) == 0:
        return None
    covariance = np.cov(port_returns, spy_returns)[0][1]
    return float(covariance / np.var(spy_returns))


def build_risk_metrics(db: Session, *, lookback_days: int = 365) -> RiskMetricsData:
    lookback_days = max(30, min(int(lookback_days), 1825))
    end = date.today()
    start = end - timedelta(days=lookback_days)

    accounts = _investment_accounts(db)
    account_ids = [a.id for a in accounts]

    twr_series = build_twr_series(db, account_ids, start, end)
    risk_free_rate_pct = get_cached_risk_free_rate(db)

    if len(twr_series) < MIN_DATA_POINTS:
        return RiskMetricsData(
            lookback_days=lookback_days,
            as_of=end.isoformat(),
            volatility_pct=None, sharpe_ratio=None, var_95_pct=None, var_99_pct=None,
            max_drawdown_pct=None, drawdown_duration_days=None, beta_vs_spy=None,
            cagr_pct=None, twr_pct=None, mwr_pct=None,
            risk_free_rate_pct=risk_free_rate_pct, data_points=len(twr_series),
        )

    growth_index = [p.growth_index for p in twr_series]
    daily_returns = _daily_returns(growth_index)

    volatility = float(np.std(daily_returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) * 100
    mean_daily = float(np.mean(daily_returns))
    annualized_return = mean_daily * TRADING_DAYS_PER_YEAR
    sharpe = (
        (annualized_return - risk_free_rate_pct / 100) / (volatility / 100)
        if volatility > 0 else None
    )
    var_95 = float(-np.percentile(daily_returns, 5)) * 100
    var_99 = float(-np.percentile(daily_returns, 1)) * 100
    max_dd_pct, dd_duration = _max_drawdown(growth_index)
    beta = _compute_beta(db, twr_series)
    cagr = build_cagr(twr_series)
    twr_pct = (growth_index[-1] / growth_index[0] - 1) * 100 if growth_index[0] else None
    mwr_pct = build_mwr_xirr(db, account_ids, start, end)

    return RiskMetricsData(
        lookback_days=lookback_days,
        as_of=end.isoformat(),
        volatility_pct=round(volatility, 2),
        sharpe_ratio=round(sharpe, 2) if sharpe is not None else None,
        var_95_pct=round(var_95, 2),
        var_99_pct=round(var_99, 2),
        max_drawdown_pct=round(max_dd_pct, 2) if max_dd_pct is not None else None,
        drawdown_duration_days=dd_duration,
        beta_vs_spy=round(beta, 2) if beta is not None else None,
        cagr_pct=round(cagr, 2) if cagr is not None else None,
        twr_pct=round(twr_pct, 2) if twr_pct is not None else None,
        mwr_pct=round(mwr_pct, 2) if mwr_pct is not None else None,
        risk_free_rate_pct=risk_free_rate_pct,
        data_points=len(twr_series),
    )
