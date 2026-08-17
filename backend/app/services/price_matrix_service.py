# backend/app/services/price_matrix_service.py
"""
Price/weight data access + basic portfolio stats: resolves which held
tickers have usable price history, builds the date-aligned price matrix used
for mean/covariance estimation, computes current portfolio weights from
holdings, and derives annualized expected return/volatility/Sharpe from a
weight vector.

Extracted from optimization_service.py (previously private, `_`-prefixed
helpers) into its own module so other services can depend on this data-access
layer without reaching into optimization_service.py's private API.
"""
from __future__ import annotations

from datetime import date

import numpy as np
from sqlalchemy.orm import Session

from app.models import Holding, MarketPrice, Security
from app.services.investment_service import (
    _investment_accounts,
    account_gross_holdings,
    scaled_holding_market_value,
)

TRADING_DAYS_PER_YEAR = 365


def priceable_tickers(db: Session, tickers: list[str], start: date, end: date) -> list[str]:
    """Held tickers that have at least one MarketPrice row in the lookback
    window. A single ticker yfinance can't resolve (money-market funds,
    unusual symbols) shouldn't disable optimization for the rest of the
    book — drop it here so `tickers` only contains names `price_matrix` can
    actually use."""
    if not tickers:
        return []
    rows = (
        db.query(MarketPrice.ticker)
        .filter(MarketPrice.ticker.in_(tickers), MarketPrice.price_date >= start, MarketPrice.price_date <= end)
        .distinct()
        .all()
    )
    priceable = {row[0] for row in rows}
    return [t for t in tickers if t in priceable]


def held_tickers(db: Session, account_ids: list[int]) -> list[str]:
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


def price_matrix(db: Session, tickers: list[str], start: date, end: date) -> tuple[list[date], np.ndarray]:
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


def current_weights(db: Session, account_ids: list[int], tickers: list[str]) -> dict[str, float]:
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


def portfolio_stats(
    weights: np.ndarray, mean_returns: np.ndarray, cov: np.ndarray, risk_free_rate_pct: float
) -> tuple[float, float, float | None]:
    expected_return = float(np.dot(weights, mean_returns)) * TRADING_DAYS_PER_YEAR
    volatility = float(np.sqrt(weights @ cov @ weights)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (expected_return - risk_free_rate_pct / 100) / volatility if volatility > 0 else None
    return expected_return * 100, volatility * 100, sharpe
