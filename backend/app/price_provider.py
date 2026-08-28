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
            closes = data[ticker]["Close"]
        except KeyError:
            result[ticker] = []
            continue
        result[ticker] = [
            (idx.date(), Decimal(str(round(float(value), 6))))
            for idx, value in closes.items()
            if value == value  # drop NaN (no print that day for this ticker)
        ]
    return result


def fetch_sectors(tickers: list[str]) -> dict[str, str | None]:
    """
    Best-effort sector lookup, one `Ticker.info` call per symbol (yfinance has
    no batch endpoint for this). Callers persist the result, so this runs once
    per holding rather than per request. A symbol yfinance can't classify —
    crypto, money-market funds, odd tickers — maps to None; that's expected,
    not an error, so failures are swallowed per ticker rather than aborting
    the batch.
    """
    sectors: dict[str, str | None] = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info or {}
            sector = info.get("sector")
            sectors[ticker] = str(sector) if sector else None
        except Exception:
            sectors[ticker] = None
    return sectors
