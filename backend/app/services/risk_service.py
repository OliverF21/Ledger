# backend/app/services/risk_service.py
"""
Portfolio risk & performance metrics: Sharpe ratio, max drawdown, and beta vs.
SPY — computed from the TWR growth-of-$1 series (app.services.returns_service)
so cash flows don't distort them, plus the cached risk-free rate
(app.risk_free_rate) and SPY daily closes (MarketPrice).

Volatility and VaR are a separate, independent calculation — see the
"Backtest" section below and
docs/superpowers/specs/2026-08-13-var-backtest-design.md. They do NOT use the
TWR series: they backtest today's actual Plaid holdings against real
MarketPrice history instead of the short BalanceSnapshot window, so they stay
meaningful even for a recently-linked account. Sharpe still divides by its
own short-window volatility, computed separately below and NOT the same
number as the displayed volatility_pct — see build_risk_metrics for why
that's an intentional, labeled divergence rather than an inconsistency.
Drawdown, beta, CAGR, TWR, and MWR are unchanged and still work exactly as
before.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models import Holding, MarketPrice, Security
from app.risk_free_rate import get_cached_risk_free_rate
from app.services.investment_service import (
    _investment_accounts,
    account_gross_holdings,
    scaled_holding_market_value,
)
from app.services.price_matrix_service import priceable_tickers
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


@dataclass(frozen=True)
class VarHorizon:
    """One rolling window's historical VaR, in both units — see the VaR
    section below for how this is computed."""
    days: int
    var_95_pct: float | None
    var_95_dollar: float | None
    var_99_pct: float | None
    var_99_dollar: float | None


@dataclass(frozen=True)
class RiskMetricsData:
    # ── from the real TWR/BalanceSnapshot series (unchanged) ───────────────
    lookback_days: int
    as_of: str
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    drawdown_duration_days: int | None
    beta_vs_spy: float | None
    cagr_pct: float | None
    twr_pct: float | None
    mwr_pct: float | None
    risk_free_rate_pct: float
    data_points: int
    # ── backtest of current holdings vs. real MarketPrice history, see
    #    build_backtest_metrics — volatility_pct here is NOT the same
    #    calculation sharpe_ratio's denominator uses (see module docstring) ──
    volatility_pct: float | None
    var_horizons: list[VarHorizon]
    var_data_points: int
    var_excluded_tickers: list[str]
    var_coverage_pct: float | None
    portfolio_value_used: float | None


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


def build_risk_metrics(db: Session, *, lookback_days: int = 365) -> RiskMetricsData:
    lookback_days = max(30, min(int(lookback_days), 1825))
    end = date.today()
    start = end - timedelta(days=lookback_days)

    accounts = _investment_accounts(db)
    account_ids = [a.id for a in accounts]

    twr_series = build_twr_series(db, account_ids, start, end)
    risk_free_rate_pct = get_cached_risk_free_rate(db)
    # Independent of twr_series/BalanceSnapshot — computed even when the real
    # account history below is too short to trust, since it backtests today's
    # holdings against MarketPrice history instead. Feeds the displayed
    # volatility_pct AND var_horizons from the same series.
    backtest = build_backtest_metrics(db, account_ids)

    if len(twr_series) < MIN_DATA_POINTS:
        return RiskMetricsData(
            lookback_days=lookback_days,
            as_of=end.isoformat(),
            sharpe_ratio=None,
            max_drawdown_pct=None, drawdown_duration_days=None, beta_vs_spy=None,
            cagr_pct=None, twr_pct=None, mwr_pct=None,
            risk_free_rate_pct=risk_free_rate_pct, data_points=len(twr_series),
            volatility_pct=backtest.volatility_pct,
            var_horizons=backtest.var_horizons,
            var_data_points=backtest.var_data_points,
            var_excluded_tickers=backtest.var_excluded_tickers,
            var_coverage_pct=backtest.var_coverage_pct,
            portfolio_value_used=backtest.portfolio_value_used,
        )

    growth_index = [p.growth_index for p in twr_series]
    daily_returns = _daily_returns(growth_index)

    if len(twr_series) >= MIN_ANNUALIZED_METRICS_POINTS:
        # Sharpe's own volatility, from the real short-window series — kept
        # deliberately separate from the displayed volatility_pct (backtest,
        # below). Diverging is intentional here, not a bug: Sharpe pairs
        # trailing real return with trailing real risk (self-consistent),
        # while the displayed tile answers "how risky is my current
        # allocation" over a much longer real price history. See module
        # docstring. Not touching this pairing further until Sharpe itself
        # is revisited.
        sharpe_volatility = float(np.std(daily_returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) * 100
        mean_daily = float(np.mean(daily_returns))
        annualized_return = mean_daily * TRADING_DAYS_PER_YEAR
        sharpe = (
            (annualized_return - risk_free_rate_pct / 100) / (sharpe_volatility / 100)
            if sharpe_volatility > 0 else None
        )
    else:
        sharpe = None
    max_dd_pct, dd_duration = _max_drawdown(twr_series)
    beta = _compute_beta(db, twr_series)
    cagr = build_cagr(twr_series)
    twr_pct = (growth_index[-1] / growth_index[0] - 1) * 100 if growth_index[0] else None
    mwr_pct = build_mwr_xirr(db, account_ids, start, end)

    return RiskMetricsData(
        lookback_days=lookback_days,
        as_of=end.isoformat(),
        sharpe_ratio=round(sharpe, 2) if sharpe is not None else None,
        max_drawdown_pct=round(max_dd_pct, 2) if max_dd_pct is not None else None,
        drawdown_duration_days=dd_duration,
        beta_vs_spy=round(beta, 2) if beta is not None else None,
        cagr_pct=round(cagr, 2) if cagr is not None else None,
        twr_pct=round(twr_pct, 2) if twr_pct is not None else None,
        mwr_pct=round(mwr_pct, 2) if mwr_pct is not None else None,
        risk_free_rate_pct=risk_free_rate_pct,
        data_points=len(twr_series),
        volatility_pct=backtest.volatility_pct,
        var_horizons=backtest.var_horizons,
        var_data_points=backtest.var_data_points,
        var_excluded_tickers=backtest.var_excluded_tickers,
        var_coverage_pct=backtest.var_coverage_pct,
        portfolio_value_used=backtest.portfolio_value_used,
    )


# ════════════════════════════════════════════════════════════════════════════
# Backtest (volatility + VaR) — everything below is independent of everything
# above.
#
# Instead of the real account's short BalanceSnapshot/TWR history, this
# backtests TODAY'S actual Plaid holdings (dollar-weighted, margin-scaled —
# same valuation optimization_service.py's optimizer uses) against up to
# ~3yr of real MarketPrice daily closes (already pulled for the optimizer,
# backfilled from yfinance by price_sync_service.py). Both volatility_pct and
# var_horizons come from the exact same portfolio_log_returns series, so they
# can't disagree with each other about what "current risk" means.
#
# Two things this section does differently from optimization_service.py's
# _price_matrix(), on purpose:
#   1. Log returns, not simple returns — VaR needs multi-day horizons, and
#      log returns are time-additive (an N-day log return is just the sum of
#      N daily log returns), so a rolling sum gives the N-day distribution
#      directly. No compounding-product step needed. Volatility's √T
#      annualization is also on firmer footing with log returns, whose
#      variance scales linearly with time under a random-walk assumption —
#      only an approximation for simple returns.
#   2. Union of each ticker's price dates, not their intersection —
#      _price_matrix() intersects every ticker's dates, so one thin-history
#      ticker (e.g. a fund that IPO'd 25 days ago) truncates the ENTIRE
#      portfolio's window down to match it. Verified against a real 57-ticker
#      portfolio: this collapsed a 3yr window down to 24 days. Instead, each
#      day's portfolio return here is the weighted average of whichever
#      tickers actually have a price that day, renormalized to the tickers
#      present — a young ticker just contributes NaN before it existed
#      instead of vetoing everyone else's history.
#
# See docs/superpowers/specs/2026-08-13-var-backtest-design.md for the full
# design writeup and the real-data verification this section is based on
# (backend/verify_var.py).
# ════════════════════════════════════════════════════════════════════════════

BACKTEST_LOOKBACK_DAYS = 1100  # ~3yr, matches MarketPrice's backfill depth (price_sync_service.BACKFILL_DAYS)
VAR_HORIZON_DAYS = [1, 5, 30]
VAR_CONFIDENCES = [95, 99]
MIN_BACKTEST_DATA_POINTS = 30
# A day only counts toward the backtest if at least this much of the
# portfolio's weight actually has a price that day — otherwise one or two
# thinly-priced tickers being briefly absent could let a tiny sliver of the
# book dominate that day's return.
MIN_DAY_COVERAGE = 0.5


@dataclass(frozen=True)
class _BacktestResult:
    volatility_pct: float | None
    var_horizons: list[VarHorizon]
    var_data_points: int
    var_excluded_tickers: list[str]
    var_coverage_pct: float | None
    portfolio_value_used: float | None


def _held_ticker_values(db: Session, account_ids: list[int]) -> dict[str, float]:
    """Dollar value per ticker from current Plaid holdings — same margin-scaled
    valuation as optimization_service.py's optimizer uses for its weights."""
    accounts_by_id = {a.id: a for a in _investment_accounts(db) if a.id in account_ids}
    holdings = (
        db.query(Holding)
        .join(Security)
        .filter(
            Holding.account_id.in_(account_ids),
            Security.ticker_symbol.isnot(None),
            Security.is_cash_equivalent.is_(False),
        )
        .all()
        if account_ids
        else []
    )
    gross_by_account = account_gross_holdings(holdings)
    value_by_ticker: dict[str, float] = {}
    for h in holdings:
        value = scaled_holding_market_value(h, accounts_by_id[h.account_id], gross_by_account)
        value_by_ticker[h.security.ticker_symbol] = value_by_ticker.get(h.security.ticker_symbol, 0.0) + value
    return value_by_ticker


def _backtest_portfolio_log_returns(
    db: Session, tickers: list[str], weights: dict[str, float], start: date, end: date
) -> pd.Series:
    """
    Daily portfolio log-return series built from the UNION of every ticker's
    price dates. Each day's return is the weighted average of whichever
    tickers actually have a price that day, with weights renormalized to the
    tickers present — see the section header above for why.
    """
    rows = (
        db.query(MarketPrice.ticker, MarketPrice.price_date, MarketPrice.close_price)
        .filter(MarketPrice.ticker.in_(tickers), MarketPrice.price_date >= start, MarketPrice.price_date <= end)
        .all()
    )
    prices = pd.DataFrame(rows, columns=["ticker", "date", "close"]).astype({"close": float})
    price_frame = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    price_frame = price_frame.reindex(columns=tickers)

    log_return_frame = np.log(price_frame / price_frame.shift(1))

    weights_series = pd.Series(weights)
    present = log_return_frame.notna()
    coverage = present.mul(weights_series, axis=1).sum(axis=1)
    weighted_returns = log_return_frame.fillna(0.0).mul(weights_series, axis=1).sum(axis=1)

    ok = coverage >= MIN_DAY_COVERAGE
    return (weighted_returns[ok] / coverage[ok]).dropna()


def _var_horizon(range_returns: pd.Series, days: int, portfolio_value: float) -> VarHorizon:
    """95%/99% historical VaR for one rolling window, in both % and $."""
    values: dict[int, tuple[float, float]] = {}
    for confidence in VAR_CONFIDENCES:
        log_threshold = float(np.percentile(range_returns, 100 - confidence))
        # exp(x)-1 rather than the raw log value — negligible at 1 day,
        # matters more by 30 (see section header).
        pct_loss = float(-(np.exp(log_threshold) - 1) * 100)
        dollar_loss = pct_loss / 100 * portfolio_value
        values[confidence] = (pct_loss, dollar_loss)
    return VarHorizon(
        days=days,
        var_95_pct=round(values[95][0], 2),
        var_95_dollar=round(values[95][1], 2),
        var_99_pct=round(values[99][0], 2),
        var_99_dollar=round(values[99][1], 2),
    )


def build_backtest_metrics(db: Session, account_ids: list[int]) -> _BacktestResult:
    """Entry point for the backtest section — called once from build_risk_metrics."""
    value_by_ticker = _held_ticker_values(db, account_ids)
    if not value_by_ticker:
        return _BacktestResult(volatility_pct=None, var_horizons=[], var_data_points=0,
                                var_excluded_tickers=[], var_coverage_pct=None, portfolio_value_used=None)

    portfolio_value = sum(value_by_ticker.values())
    if portfolio_value <= 0:
        return _BacktestResult(volatility_pct=None, var_horizons=[], var_data_points=0,
                                var_excluded_tickers=[], var_coverage_pct=None,
                                portfolio_value_used=round(portfolio_value, 2))

    end = date.today()
    start = end - timedelta(days=BACKTEST_LOOKBACK_DAYS)
    all_tickers = sorted(value_by_ticker)
    tickers = priceable_tickers(db, all_tickers, start, end)
    excluded_tickers = [t for t in all_tickers if t not in tickers]

    if not tickers:
        return _BacktestResult(volatility_pct=None, var_horizons=[], var_data_points=0,
                                var_excluded_tickers=excluded_tickers, var_coverage_pct=0.0,
                                portfolio_value_used=round(portfolio_value, 2))

    priceable_value = sum(value_by_ticker[t] for t in tickers)
    coverage_pct = priceable_value / portfolio_value * 100
    weights = {t: value_by_ticker[t] / priceable_value for t in tickers}

    portfolio_log_returns = _backtest_portfolio_log_returns(db, tickers, weights, start, end)
    if len(portfolio_log_returns) < MIN_BACKTEST_DATA_POINTS:
        return _BacktestResult(volatility_pct=None, var_horizons=[], var_data_points=len(portfolio_log_returns),
                                var_excluded_tickers=excluded_tickers, var_coverage_pct=round(coverage_pct, 1),
                                portfolio_value_used=round(portfolio_value, 2))

    volatility_pct = float(np.std(portfolio_log_returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) * 100

    horizons: list[VarHorizon] = []
    for days in VAR_HORIZON_DAYS:
        range_returns = portfolio_log_returns.rolling(window=days).sum().dropna()
        if len(range_returns) < MIN_BACKTEST_DATA_POINTS:
            continue  # gated independently — e.g. enough history for 1d/5d but not yet 30d
        horizons.append(_var_horizon(range_returns, days, portfolio_value))

    return _BacktestResult(
        volatility_pct=round(volatility_pct, 2),
        var_horizons=horizons,
        var_data_points=len(portfolio_log_returns),
        var_excluded_tickers=excluded_tickers,
        var_coverage_pct=round(coverage_pct, 1),
        portfolio_value_used=round(portfolio_value, 2),
    )
