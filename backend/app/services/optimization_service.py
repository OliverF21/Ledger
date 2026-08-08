# backend/app/services/optimization_service.py
"""
Suggested max-Sharpe portfolio allocation across currently-held tickers, using
a mean-variance optimizer (scipy SLSQP rather than PyPortfolioOpt/cvxpy — see
plan doc for why: cvxpy's solver backends are a known headache to bundle into
the PyInstaller desktop build, and SLSQP is more than sufficient for this
book's size, ~5-30 holdings).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from scipy.optimize import minimize
from sqlalchemy.orm import Session

from app.models import Holding, MarketPrice, Security
from app.risk_free_rate import get_cached_risk_free_rate
from app.services.investment_service import (
    _investment_accounts,
    account_gross_holdings,
    scaled_holding_market_value,
)

TRADING_DAYS_PER_YEAR = 365
MIN_LOOKBACK_ROWS = 30


@dataclass(frozen=True)
class TickerWeight:
    ticker: str
    current_weight_pct: float
    suggested_weight_pct: float


@dataclass(frozen=True)
class OptimizationData:
    tickers: list[TickerWeight]
    current_expected_return_pct: float | None
    current_volatility_pct: float | None
    current_sharpe: float | None
    suggested_expected_return_pct: float | None
    suggested_volatility_pct: float | None
    suggested_sharpe: float | None
    data_points: int
    insufficient_data: bool


def _empty_result(data_points: int = 0) -> OptimizationData:
    return OptimizationData(
        tickers=[], current_expected_return_pct=None, current_volatility_pct=None, current_sharpe=None,
        suggested_expected_return_pct=None, suggested_volatility_pct=None, suggested_sharpe=None,
        data_points=data_points, insufficient_data=True,
    )


def _held_tickers(db: Session, account_ids: list[int]) -> list[str]:
    if not account_ids:
        return []
    rows = (
        db.query(Security.ticker_symbol)
        .join(Holding, Holding.security_id == Security.id)
        .filter(
            Holding.account_id.in_(account_ids),
            Security.ticker_symbol.isnot(None),
            Security.is_cash_equivalent.is_(False),
        )
        .distinct()
        .all()
    )
    return sorted({row[0] for row in rows if row[0]})


def _price_matrix(db: Session, tickers: list[str], start: date, end: date) -> tuple[list[date], np.ndarray]:
    """Rows = dates common to every ticker, columns = tickers (in `tickers` order)."""
    rows = (
        db.query(MarketPrice.ticker, MarketPrice.price_date, MarketPrice.close_price)
        .filter(MarketPrice.ticker.in_(tickers), MarketPrice.price_date >= start, MarketPrice.price_date <= end)
        .all()
    )
    by_ticker: dict[str, dict[date, float]] = {t: {} for t in tickers}
    for ticker, price_date, close_price in rows:
        by_ticker[ticker][price_date] = float(close_price)

    if not all(by_ticker.values()):
        return [], np.array([])
    common_dates = sorted(set.intersection(*(set(d.keys()) for d in by_ticker.values())))
    if not common_dates:
        return [], np.array([])

    matrix = np.array([[by_ticker[t][d] for t in tickers] for d in common_dates])
    return common_dates, matrix


def _current_weights(db: Session, account_ids: list[int], tickers: list[str]) -> dict[str, float]:
    accounts_by_id = {a.id: a for a in _investment_accounts(db) if a.id in account_ids}
    holdings = (
        db.query(Holding)
        .join(Security)
        .filter(Holding.account_id.in_(account_ids), Security.ticker_symbol.in_(tickers))
        .all()
        if account_ids else []
    )
    gross_by_account = account_gross_holdings(holdings)
    value_by_ticker: dict[str, float] = {t: 0.0 for t in tickers}
    for h in holdings:
        value = scaled_holding_market_value(h, accounts_by_id[h.account_id], gross_by_account)
        value_by_ticker[h.security.ticker_symbol] += value
    total = sum(value_by_ticker.values())
    if total <= 0:
        return {t: 0.0 for t in tickers}
    return {t: v / total * 100 for t, v in value_by_ticker.items()}


def _portfolio_stats(
    weights: np.ndarray, mean_returns: np.ndarray, cov: np.ndarray, risk_free_rate_pct: float
) -> tuple[float, float, float | None]:
    expected_return = float(np.dot(weights, mean_returns)) * TRADING_DAYS_PER_YEAR
    volatility = float(np.sqrt(weights @ cov @ weights)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (expected_return - risk_free_rate_pct / 100) / volatility if volatility > 0 else None
    return expected_return * 100, volatility * 100, sharpe


def build_optimization_suggestion(db: Session, *, lookback_days: int = 365) -> OptimizationData:
    lookback_days = max(90, min(int(lookback_days), 1825))
    end = date.today()
    start = end - timedelta(days=lookback_days)

    accounts = _investment_accounts(db)
    account_ids = [a.id for a in accounts]
    tickers = _held_tickers(db, account_ids)
    if len(tickers) < 2:
        return _empty_result()

    dates, prices = _price_matrix(db, tickers, start, end)
    if len(dates) < MIN_LOOKBACK_ROWS:
        return _empty_result(data_points=len(dates))

    returns = prices[1:] / prices[:-1] - 1
    mean_returns = returns.mean(axis=0)
    cov = np.cov(returns, rowvar=False)
    risk_free_rate_pct = get_cached_risk_free_rate(db)

    current_weights_pct = _current_weights(db, account_ids, tickers)
    current_weights = np.array([current_weights_pct[t] / 100 for t in tickers])
    current_return, current_vol, current_sharpe = _portfolio_stats(current_weights, mean_returns, cov, risk_free_rate_pct)

    n = len(tickers)

    def neg_sharpe(weights: np.ndarray) -> float:
        ret = np.dot(weights, mean_returns) * TRADING_DAYS_PER_YEAR
        vol = np.sqrt(weights @ cov @ weights) * np.sqrt(TRADING_DAYS_PER_YEAR)
        if vol == 0:
            return 0.0
        return -(ret - risk_free_rate_pct / 100) / vol

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0.0, 1.0)] * n
    initial = np.array([1.0 / n] * n)

    result = minimize(neg_sharpe, initial, method="SLSQP", bounds=bounds, constraints=constraints)
    suggested_weights = result.x if result.success else initial
    suggested_return, suggested_vol, suggested_sharpe = _portfolio_stats(suggested_weights, mean_returns, cov, risk_free_rate_pct)

    ticker_weights = [
        TickerWeight(
            ticker=t,
            current_weight_pct=round(current_weights_pct[t], 2),
            suggested_weight_pct=round(float(suggested_weights[i]) * 100, 2),
        )
        for i, t in enumerate(tickers)
    ]

    return OptimizationData(
        tickers=ticker_weights,
        current_expected_return_pct=round(current_return, 2),
        current_volatility_pct=round(current_vol, 2),
        current_sharpe=round(current_sharpe, 2) if current_sharpe is not None else None,
        suggested_expected_return_pct=round(suggested_return, 2),
        suggested_volatility_pct=round(suggested_vol, 2),
        suggested_sharpe=round(suggested_sharpe, 2) if suggested_sharpe is not None else None,
        data_points=len(dates),
        insufficient_data=False,
    )
