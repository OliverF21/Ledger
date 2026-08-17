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

from app.risk_free_rate import get_cached_risk_free_rate
from app.services.investment_service import _investment_accounts
from app.services.price_matrix_service import (
    current_weights,
    held_tickers,
    portfolio_stats,
    price_matrix,
    priceable_tickers,
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


def build_optimization_suggestion(db: Session, *, lookback_days: int = 365) -> OptimizationData:
    lookback_days = max(90, min(int(lookback_days), 1825))
    end = date.today()
    start = end - timedelta(days=lookback_days)

    accounts = _investment_accounts(db)
    account_ids = [a.id for a in accounts]
    tickers = held_tickers(db, account_ids)
    if len(tickers) < 2:
        return _empty_result()

    tickers = priceable_tickers(db, tickers, start, end)
    if len(tickers) < 2:
        return _empty_result()

    dates, prices = price_matrix(db, tickers, start, end)
    if len(dates) < MIN_LOOKBACK_ROWS:
        return _empty_result(data_points=len(dates))

    returns = prices[1:] / prices[:-1] - 1
    mean_returns = returns.mean(axis=0)
    cov = np.cov(returns, rowvar=False)
    risk_free_rate_pct = get_cached_risk_free_rate(db)

    current_weights_pct = current_weights(db, account_ids, tickers)
    current_weight_fractions = np.array([current_weights_pct[t] / 100 for t in tickers])
    current_return, current_vol, current_sharpe = portfolio_stats(current_weight_fractions, mean_returns, cov, risk_free_rate_pct)

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
    suggested_return, suggested_vol, suggested_sharpe = portfolio_stats(suggested_weights, mean_returns, cov, risk_free_rate_pct)

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
