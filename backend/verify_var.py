# backend/verify_var.py
"""
Standalone verification script for the log-return historical VaR design
(see chat / upcoming spec doc under docs/superpowers/specs/). Same
    percentile-of-rolling-log-returns method as the example_var.py reference
script, but:
  - pulls tickers + weights from your actual current Plaid holdings
    (dollar-weighted, margin-scaled) instead of an equal-weighted fixed list
  - uses MarketPrice (already backfilled from yfinance by
    price_sync_service.py) instead of a fresh yf.download call
  - reports 1/5/30-day VaR at 95%/99%, in both % and $

Not wired into the app yet — this is purely to sanity-check the numbers
before risk_service.py gets rewritten to use this method. Run from backend/
with the venv active:
    python verify_var.py                       # backend/ledger.db
    LEDGER_USE_APPDATA=1 python verify_var.py   # desktop app's DB (must be closed first)
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap_desktop

bootstrap_desktop()

from app.database import SessionLocal
from app.models import Holding, MarketPrice, Security
from app.services.investment_service import (
    _investment_accounts,
    account_gross_holdings,
    scaled_holding_market_value,
)
from app.services.price_matrix_service import priceable_tickers

LOOKBACK_DAYS = 1100  # ~3yr, matches MarketPrice's actual backfill depth (BACKFILL_DAYS)
HORIZON_DAYS = [1, 5, 30]
CONFIDENCES = [95, 99]
MIN_PRICE_ROWS = 30
# A day only counts if at least this much of the portfolio's weight actually
# has a price that day — otherwise one or two thinly-priced tickers being
# absent could let a tiny sliver of the book dominate that day's return.
MIN_DAY_COVERAGE = 0.5


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


def _portfolio_log_returns(
    db: Session, tickers: list[str], weights: dict[str, float], start: date, end: date
) -> tuple[pd.Series, pd.Series]:
    """
    Daily portfolio log-return series built from the UNION of every ticker's
    price dates, not their intersection. A ticker with a short history (e.g.
    a fund that IPO'd 25 days ago) contributes NaN on days before it existed
    instead of truncating every other ticker's history down to match it —
    each day's return is the weighted average of whichever tickers actually
    have a price that day, with weights renormalized to the tickers present.

    Returns (portfolio_log_returns, coverage) where coverage is the fraction
    of total portfolio weight actually priced on each surviving day.
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
    portfolio_log_returns = (weighted_returns[ok] / coverage[ok]).dropna()
    return portfolio_log_returns, coverage[ok]


def main() -> None:
    db = SessionLocal()
    try:
        accounts = _investment_accounts(db)
        account_ids = [a.id for a in accounts]

        value_by_ticker = _held_ticker_values(db, account_ids)
        if not value_by_ticker:
            print("No priceable holdings found — link an investment account and sync first.")
            return

        end = date.today()
        start = end - timedelta(days=LOOKBACK_DAYS)

        tickers = priceable_tickers(db, sorted(value_by_ticker), start, end)
        if not tickers:
            print("None of the held tickers have MarketPrice history yet — trigger a sync "
                  "(price_sync_service.sync_market_prices) first.")
            return

        # Weights normalized over the priceable subset only (tickers yfinance
        # can't resolve get dropped and the rest scaled up) — same behavior
        # as optimization_service.py's optimizer.
        portfolio_value = sum(value_by_ticker.values())
        raw_weights = {t: value_by_ticker.get(t, 0.0) for t in tickers}
        total_weight = sum(raw_weights.values())
        weights = {t: v / total_weight for t, v in raw_weights.items()}

        print(f"Tickers:  {tickers}")
        print(f"Weights:  { {t: round(w * 100, 2) for t, w in weights.items()} }")
        print(f"Portfolio value used for $ VaR: ${portfolio_value:,.2f}")

        portfolio_log_returns, coverage = _portfolio_log_returns(db, tickers, weights, start, end)
        if len(portfolio_log_returns) < MIN_PRICE_ROWS:
            print(f"Only {len(portfolio_log_returns)} usable days (>= {MIN_DAY_COVERAGE:.0%} weight priced) — too little history to trust these numbers yet.")
            return

        thin_days = int((coverage < 0.999).sum())
        print(
            f"Price history: {portfolio_log_returns.index[0]} -> {portfolio_log_returns.index[-1]} "
            f"({len(portfolio_log_returns)} days, {thin_days} with partial coverage, "
            f"min coverage {coverage.min():.1%})\n"
        )

        print(f"{'Horizon':>8} {'Conf':>6} {'Log %':>10} {'Real %':>10} {'Dollar':>14}")
        for horizon in HORIZON_DAYS:
            # Logs are time-additive: an N-day log return is just the sum of N
            # daily log returns, so a rolling sum gives the N-day distribution
            # directly — no compounding-product step needed (this is the
            # whole reason to use log returns here, per example_var.py).
            range_returns = portfolio_log_returns.rolling(window=horizon).sum().dropna()
            if range_returns.empty:
                print(f"{horizon:>7}d   -- not enough history for this window yet --")
                continue
            for confidence in CONFIDENCES:
                log_threshold = np.percentile(range_returns, 100 - confidence)
                # Convert the log-return threshold back to a real percentage
                # (exp(x)-1) instead of using the raw log value directly, like
                # the reference script does — negligible at 1 day, matters
                # more by 30.
                pct_loss = -(np.exp(log_threshold) - 1) * 100
                dollar_loss = pct_loss / 100 * portfolio_value
                print(
                    f"{horizon:>7}d {confidence:>5}% {log_threshold * 100:>9.2f}% "
                    f"{pct_loss:>9.2f}% ${dollar_loss:>12,.2f}"
                )
    finally:
        db.close()


if __name__ == "__main__":
    main()
