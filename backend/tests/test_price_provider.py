from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from app.price_provider import fetch_daily_closes


def _multi_ticker_frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"])
    columns = pd.MultiIndex.from_tuples([
        ("AAPL", "Close"), ("AAPL", "Open"),
        ("SPY", "Close"), ("SPY", "Open"),
    ])
    data = [
        [192.53, 190.0, 470.10, 468.0],
        [float("nan"), 192.0, 471.20, 470.0],  # AAPL had no print this day in the fixture
        [194.00, 193.0, 472.50, 471.0],
    ]
    return pd.DataFrame(data, index=idx, columns=columns)


def test_fetch_daily_closes_parses_multi_ticker_frame(monkeypatch):
    monkeypatch.setattr("app.price_provider.yf.download", lambda *a, **k: _multi_ticker_frame())

    result = fetch_daily_closes(["AAPL", "SPY"], start=date(2026, 1, 2), end=date(2026, 1, 5))

    assert result["AAPL"] == [
        (date(2026, 1, 2), Decimal("192.53")),
        (date(2026, 1, 4), Decimal("194.0")),
    ]
    assert result["SPY"] == [
        (date(2026, 1, 2), Decimal("470.1")),
        (date(2026, 1, 3), Decimal("471.2")),
        (date(2026, 1, 4), Decimal("472.5")),
    ]


def test_fetch_daily_closes_empty_tickers_returns_empty_dict():
    assert fetch_daily_closes([], start=date(2026, 1, 1), end=date(2026, 1, 2)) == {}


def test_fetch_daily_closes_missing_ticker_returns_empty_list(monkeypatch):
    monkeypatch.setattr("app.price_provider.yf.download", lambda *a, **k: _multi_ticker_frame())

    result = fetch_daily_closes(["AAPL", "DOESNOTEXIST"], start=date(2026, 1, 2), end=date(2026, 1, 5))

    assert result["DOESNOTEXIST"] == []
