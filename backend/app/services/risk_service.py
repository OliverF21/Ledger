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
# Annualized/percentile metrics (volatility, Sharpe, VaR) extrapolate a full
# year's risk from the observed daily-return sample; with only a handful of
# points that extrapolation is mostly noise (e.g. 4 daily returns can produce
# a Sharpe of 5+ with no statistical meaning). Require about a month of daily
# data before surfacing them. Max drawdown/duration/CAGR/TWR/MWR degrade more
# gracefully with less data and stay gated on the lower MIN_DATA_POINTS floor.
MIN_ANNUALIZED_METRICS_POINTS = 21
# CAGR / Sharpe annualize a short observed span into a full-year rate. Extrapolating
# ~a month of history into "13% CAGR" is misleading — require ~a quarter of calendar
# coverage before showing annualized return tiles.
MIN_CAGR_CALENDAR_DAYS = 90


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
    series_start: str | None = None
    series_end: str | None = None
    effective_days: int | None = None


def _daily_returns(growth_index: list[float]) -> np.ndarray:
    arr = np.array(growth_index, dtype=float)
    if len(arr) < 2:
        return np.array([])
    return arr[1:] / arr[:-1] - 1


def _max_drawdown(twr_series: list[TWRPoint]) -> tuple[float | None, int | None]:
    if len(twr_series) < 2:
        return None, None
    arr = np.array([p.growth_index for p in twr_series], dtype=float)
    running_max = np.maximum.accumulate(arr)
    drawdowns = (arr - running_max) / running_max
    max_dd = float(drawdowns.min())

    trough_idx = int(drawdowns.argmin())
    peak_idx = int(np.argmax(arr[: trough_idx + 1]))
    # BalanceSnapshot rows only exist on days a sync ran, so the index gap
    # between peak and trough can undercount elapsed time whenever a sync was
    # missed — use the actual calendar-day difference instead.
    duration_days = (twr_series[trough_idx].date - twr_series[peak_idx].date).days
    return max_dd * 100, duration_days


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
    if len(spy_returns) < 2 or np.var(spy_returns, ddof=1) == 0:
        return None
    covariance = np.cov(port_returns, spy_returns, ddof=1)[0][1]
    return float(covariance / np.var(spy_returns, ddof=1))


def _empty_metrics(
    *,
    lookback_days: int,
    as_of: date,
    risk_free_rate_pct: float,
    data_points: int,
    series_start: date | None = None,
    series_end: date | None = None,
    effective_days: int | None = None,
) -> RiskMetricsData:
    return RiskMetricsData(
        lookback_days=lookback_days,
        as_of=as_of.isoformat(),
        volatility_pct=None,
        sharpe_ratio=None,
        var_95_pct=None,
        var_99_pct=None,
        max_drawdown_pct=None,
        drawdown_duration_days=None,
        beta_vs_spy=None,
        cagr_pct=None,
        twr_pct=None,
        mwr_pct=None,
        risk_free_rate_pct=risk_free_rate_pct,
        data_points=data_points,
        series_start=series_start.isoformat() if series_start else None,
        series_end=series_end.isoformat() if series_end else None,
        effective_days=effective_days,
    )


def build_risk_metrics(db: Session, *, lookback_days: int = 365) -> RiskMetricsData:
    lookback_days = max(30, min(int(lookback_days), 1825))
    end = date.today()
    start = end - timedelta(days=lookback_days)

    accounts = _investment_accounts(db)
    account_ids = [a.id for a in accounts]

    twr_series = build_twr_series(db, account_ids, start, end)
    risk_free_rate_pct = get_cached_risk_free_rate(db)

    if len(twr_series) < MIN_DATA_POINTS:
        return _empty_metrics(
            lookback_days=lookback_days,
            as_of=end,
            risk_free_rate_pct=risk_free_rate_pct,
            data_points=len(twr_series),
        )

    series_start = twr_series[0].date
    series_end = twr_series[-1].date
    effective_days = (series_end - series_start).days

    growth_index = [p.growth_index for p in twr_series]
    daily_returns = _daily_returns(growth_index)

    if len(twr_series) >= MIN_ANNUALIZED_METRICS_POINTS:
        volatility = float(np.std(daily_returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) * 100
        var_95 = float(-np.percentile(daily_returns, 5)) * 100
        var_99 = float(-np.percentile(daily_returns, 1)) * 100
    else:
        volatility = None
        var_95 = None
        var_99 = None

    max_dd_pct, dd_duration = _max_drawdown(twr_series)
    beta = _compute_beta(db, twr_series)
    twr_pct = (growth_index[-1] / growth_index[0] - 1) * 100 if growth_index[0] else None
    mwr_pct = build_mwr_xirr(db, account_ids, start, end)

    # CAGR is annualized TWR over the *observed* span. Withholding it (and Sharpe)
    # until we have enough calendar coverage avoids "13% CAGR" from ~a month of data.
    cagr = build_cagr(twr_series) if effective_days >= MIN_CAGR_CALENDAR_DAYS else None

    # Sharpe must use the same annualized return the CAGR tile shows (geometric
    # TWR), not arithmetic mean×365 — that produced positive Sharpes while
    # (TWR − rf) / vol was negative.
    sharpe = None
    if (
        cagr is not None
        and volatility is not None
        and volatility > 1e-9
        and len(twr_series) >= MIN_ANNUALIZED_METRICS_POINTS
    ):
        sharpe = (cagr / 100 - risk_free_rate_pct / 100) / (volatility / 100)

    return RiskMetricsData(
        lookback_days=lookback_days,
        as_of=end.isoformat(),
        volatility_pct=round(volatility, 2) if volatility is not None else None,
        sharpe_ratio=(
            round(sharpe, 2)
            if sharpe is not None and volatility is not None and round(volatility, 2) > 0
            else None
        ),
        var_95_pct=round(var_95, 2) if var_95 is not None else None,
        var_99_pct=round(var_99, 2) if var_99 is not None else None,
        max_drawdown_pct=round(max_dd_pct, 2) if max_dd_pct is not None else None,
        drawdown_duration_days=dd_duration,
        beta_vs_spy=round(beta, 2) if beta is not None else None,
        cagr_pct=round(cagr, 2) if cagr is not None else None,
        twr_pct=round(twr_pct, 2) if twr_pct is not None else None,
        mwr_pct=round(mwr_pct, 2) if mwr_pct is not None else None,
        risk_free_rate_pct=risk_free_rate_pct,
        data_points=len(twr_series),
        series_start=series_start.isoformat(),
        series_end=series_end.isoformat(),
        effective_days=effective_days,
    )
