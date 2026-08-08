"""
Thin wrapper around yfinance for fetching historical daily close prices.
Isolated here (mirrors plaid_service.py's pattern) so the yfinance dependency
and its quirks (batch download, pandas return type) stay in one place — the
rest of the app never imports pandas or yfinance directly.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import yfinance as yf


def fetch_daily_closes(tickers: list[str], start: date, end: date) -> dict[str, list[tuple[date, Decimal]]]:
    """
    Batch-fetch daily close prices for `tickers` over [start, end). yfinance's
    `end` is exclusive, so callers wanting `end` included should pass end+1.
    Returns {ticker: [(date, close), ...]} sorted ascending by date; a ticker
    with no data (delisted, bad symbol, no trades in range) maps to [].
    """
    if not tickers:
        return {}

    data = yf.download(
        tickers,
        start=start.isoformat(),
        end=end.isoformat(),
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    result: dict[str, list[tuple[date, Decimal]]] = {}
    for ticker in tickers:
        try:
            closes = data[ticker]["Close"] if len(tickers) > 1 else data["Close"]
        except KeyError:
            result[ticker] = []
            continue
        result[ticker] = [
            (idx.date(), Decimal(str(round(float(value), 6))))
            for idx, value in closes.items()
            if value == value  # drop NaN (no print that day for this ticker)
        ]
    return result
