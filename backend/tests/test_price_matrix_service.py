"""Unit tests for price_matrix_service.price_returns (union-of-dates NaN gaps)."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.price_matrix_service import price_returns


def test_price_returns_dense_matches_simple_pct_change():
    prices = np.array([[100.0, 50.0], [110.0, 55.0], [121.0, 44.0]])
    got = price_returns(prices)
    naive = prices[1:] / prices[:-1] - 1
    assert got == pytest.approx(naive)


def test_price_returns_keeps_equity_weekend_move_that_naive_pct_change_drops():
    # Union of BTC (has Sat) and SPY (weekday only): Saturday is NaN for SPY.
    # Naive row-wise pct_change makes Monday/SaturdayNaN = NaN, so SPY's
    # Fri→Mon return disappears. price_returns must keep it.
    # rows: Fri, Sat, Mon
    prices = np.array([
        [100.0, 10.0],   # SPY, BTC Friday
        [np.nan, 10.5],  # BTC Saturday
        [102.0, 10.8],   # Monday
    ])
    naive = prices[1:] / prices[:-1] - 1
    assert np.isnan(naive[1, 0])  # SPY Monday wiped out

    got = price_returns(prices)
    assert got[1, 0] == pytest.approx(0.02)  # 102/100 - 1
    assert got[0, 1] == pytest.approx(0.05)  # BTC Fri→Sat
    assert got[1, 1] == pytest.approx(10.8 / 10.5 - 1)


def test_price_returns_leading_nans_still_yield_later_returns():
    # Recently listed ticker: NaNs until IPO, then a real series.
    prices = np.array([
        [np.nan, 100.0],
        [np.nan, 101.0],
        [50.0, 102.0],
        [55.0, 103.0],
    ])
    got = price_returns(prices)
    assert np.isnan(got[0, 0])
    assert np.isnan(got[1, 0])
    assert got[2, 0] == pytest.approx(0.10)
    assert got[0, 1] == pytest.approx(0.01)
