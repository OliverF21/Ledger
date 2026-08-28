# backend/tests/test_risk_service.py
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from cryptography.fernet import Fernet

# risk_service imports get_cached_risk_free_rate -> app_config -> app.security,
# which raises at import time if ENCRYPTION_KEY is unset. Match the same
# workaround used by other tests that transitively touch app.security
# (e.g. tests/test_risk_free_rate.py, tests/test_app_config.py) so this file
# passes when run standalone, not just as part of the full suite.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Account, BalanceSnapshot, Base, Holding, Item, MarketPrice, Security, User  # noqa: E402
from app.services.risk_service import (  # noqa: E402
    MIN_BACKTEST_DATA_POINTS,
    _backtest_portfolio_log_returns,
    build_risk_metrics,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'risk.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def account(db_session):
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    acc = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment")
    db_session.add(acc)
    db_session.commit()
    return acc


def test_insufficient_history_returns_nones(db_session, account):
    db_session.add(BalanceSnapshot(account_id=account.id, balance=100, snapshot_date=date.today()))
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=365)
    assert data.volatility_pct is None
    assert data.sharpe_ratio is None
    assert data.data_points == 1


def test_known_series_max_drawdown_and_volatility(db_session, account):
    d0 = date.today() - timedelta(days=4)
    values = [100, 102, 101, 105, 103]  # no cash flows -> TWR growth_index == value/100
    for i, v in enumerate(values):
        db_session.add(BalanceSnapshot(account_id=account.id, balance=v, snapshot_date=d0 + timedelta(days=i)))
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=10)

    assert data.data_points == 5
    # Hand-computed: running max [100,102,102,105,105], drawdown min at day5
    # = (103-105)/105 = -1.904...%
    assert data.max_drawdown_pct == pytest.approx(-1.9, abs=0.05)
    # Trough at index 4 (day5), peak at index 3 (day4) -> 1 calendar day apart,
    # and since these are consecutive daily snapshots with no gaps, the
    # calendar-day duration matches the index difference here.
    assert data.drawdown_duration_days == 1
    # 5 points is below MIN_ANNUALIZED_METRICS_POINTS (21) -- annualized/
    # percentile metrics should be withheld as statistically meaningless,
    # while max drawdown (which degrades more gracefully) still computes.
    assert data.volatility_pct is None
    assert data.sharpe_ratio is None
    assert data.risk_free_rate_pct > 0  # falls back to DEFAULT_RISK_FREE_RATE_PCT
    # VaR is independent of this BalanceSnapshot series (see the VaR section
    # of tests below) -- no Holdings exist in this fixture, so it's empty.
    assert data.var_horizons == []


def test_annualized_metrics_populate_past_min_points_floor(db_session, account):
    # 25 daily snapshots (above MIN_ANNUALIZED_METRICS_POINTS=21) with mild
    # noise so Sharpe is well-defined and should populate.
    d0 = date.today() - timedelta(days=24)
    values = [100, 101, 100, 102, 103, 102, 104, 105, 104, 106, 107, 106, 108,
              109, 108, 110, 111, 110, 112, 113, 112, 114, 115, 114, 116]
    for i, v in enumerate(values):
        db_session.add(BalanceSnapshot(account_id=account.id, balance=v, snapshot_date=d0 + timedelta(days=i)))
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=30)

    assert data.data_points == 25
    assert data.sharpe_ratio is not None
    # Volatility and VaR no longer come from this BalanceSnapshot series --
    # see the Backtest section of tests below for their own data
    # requirements (Holdings + MarketPrice), which this fixture doesn't set up.
    assert data.volatility_pct is None
    assert data.var_horizons == []


def test_beta_uses_market_price_spy_series(db_session, account):
    d0 = date.today() - timedelta(days=5)
    portfolio_values = [100, 101, 100, 103, 104, 102]
    spy_values = [Decimal("400"), Decimal("402"), Decimal("399"), Decimal("405"), Decimal("407"), Decimal("403")]
    for i, (pv, sv) in enumerate(zip(portfolio_values, spy_values)):
        day = d0 + timedelta(days=i)
        db_session.add(BalanceSnapshot(account_id=account.id, balance=pv, snapshot_date=day))
        db_session.add(MarketPrice(ticker="SPY", price_date=day, close_price=sv))
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=10)
    assert data.beta_vs_spy is not None


def test_beta_matches_hand_computed_value(db_session, account):
    """
    Pins beta to a known value so a ddof mismatch between np.cov (default
    ddof=1) and np.var (default ddof=0) in _compute_beta can't slip back in
    undetected — the prior "is not None" check couldn't catch it.

    Portfolio daily returns are constructed as exactly 2x SPY's daily returns
    (0.05, -0.02, 0.03, -0.01 for SPY; 0.10, -0.04, 0.06, -0.02 for the
    portfolio), so true beta = cov(port, spy) / var(spy) = cov(2*spy, spy) /
    var(spy) = 2*var(spy) / var(spy) = 2.0 exactly, for *any* ddof as long as
    the same ddof is used for both cov and var. Prices are built by
    compounding those returns from a start of 100 (rounded to the DB column's
    decimal precision — 4dp for BalanceSnapshot.balance, 6dp for
    MarketPrice.close_price), which perturbs the exact ratio by <0.001%.

    With a ddof mismatch (np.cov ddof=1, np.var ddof=0), beta would compute to
    2.0 * n/(n-1) = 2.0 * 4/3 ~= 2.67 for these 4 return pairs -- verified by
    direct calculation with the same rounded prices before writing this test.
    """
    d0 = date.today() - timedelta(days=4)
    portfolio_prices = [
        Decimal("100.0000"), Decimal("110.0000"), Decimal("105.6000"),
        Decimal("111.9360"), Decimal("109.6973"),
    ]
    spy_prices = [
        Decimal("100.000000"), Decimal("105.000000"), Decimal("102.900000"),
        Decimal("105.987000"), Decimal("104.927130"),
    ]
    for i, (pv, sv) in enumerate(zip(portfolio_prices, spy_prices)):
        day = d0 + timedelta(days=i)
        db_session.add(BalanceSnapshot(account_id=account.id, balance=pv, snapshot_date=day))
        db_session.add(MarketPrice(ticker="SPY", price_date=day, close_price=sv))
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=10)

    assert data.beta_vs_spy == pytest.approx(2.0, abs=0.05)


# ════════════════════════════════════════════════════════════════════════════
# Backtest (volatility + VaR) -- independent of the tests above, which only
# set up BalanceSnapshot/TWR data. These need Holding + Security + MarketPrice
# instead, since the backtest reads current Plaid holdings, not the real
# account's balance history.
# ════════════════════════════════════════════════════════════════════════════

def _add_holding(db_session, account, ticker: str, value: float) -> None:
    security = Security(plaid_security_id=f"sec-{ticker}", ticker_symbol=ticker, is_cash_equivalent=False)
    db_session.add(security)
    db_session.flush()
    db_session.add(Holding(account_id=account.id, security_id=security.id, quantity=1, institution_value=value))


def _add_prices(db_session, ticker: str, start: date, n: int, base: float = 100.0) -> None:
    for i in range(n):
        # small deterministic wobble so returns aren't degenerately zero
        price = base + (i % 5) - 2
        db_session.add(MarketPrice(ticker=ticker, price_date=start + timedelta(days=i), close_price=price))


def test_backtest_returns_empty_when_no_holdings(db_session, account):
    data = build_risk_metrics(db_session, lookback_days=365)
    assert data.volatility_pct is None
    assert data.var_horizons == []
    assert data.var_data_points == 0
    assert data.var_excluded_tickers == []
    assert data.var_coverage_pct is None
    assert data.portfolio_value_used is None


def test_backtest_populates_with_sufficient_price_history(db_session, account):
    account.current_balance = 1000
    _add_holding(db_session, account, "AAPL", 1000)
    _add_prices(db_session, "AAPL", date.today() - timedelta(days=100), n=100)
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=365)

    assert data.var_excluded_tickers == []
    assert data.var_coverage_pct == pytest.approx(100.0)
    assert data.portfolio_value_used == pytest.approx(1000.0)
    assert data.var_data_points >= MIN_BACKTEST_DATA_POINTS
    assert data.volatility_pct is not None and data.volatility_pct > 0
    days_present = {h.days for h in data.var_horizons}
    assert days_present == {1, 5, 30}
    for h in data.var_horizons:
        assert h.var_95_pct is not None and h.var_95_pct >= 0
        assert h.var_99_pct is not None and h.var_99_pct >= h.var_95_pct
        # pct and dollar are rounded independently from the same unrounded
        # value, so allow a couple cents of double-rounding slack.
        assert h.var_95_dollar == pytest.approx(h.var_95_pct / 100 * 1000, abs=0.05)


def test_volatility_independent_of_sharpe_series(db_session, account):
    """
    volatility_pct (backtest) and sharpe_ratio's own internal volatility (real
    short-window series) are deliberately different calculations -- adding
    backtest-only data (Holding/MarketPrice) must change volatility_pct
    without moving sharpe_ratio at all, and vice versa. This is the
    regression test for that intentional divergence (see module docstring).
    """
    d0 = date.today() - timedelta(days=24)
    values = [100, 101, 100, 102, 103, 102, 104, 105, 104, 106, 107, 106, 108,
              109, 108, 110, 111, 110, 112, 113, 112, 114, 115, 114, 116]
    for i, v in enumerate(values):
        db_session.add(BalanceSnapshot(account_id=account.id, balance=v, snapshot_date=d0 + timedelta(days=i)))
    db_session.commit()

    before = build_risk_metrics(db_session, lookback_days=30)
    assert before.sharpe_ratio is not None
    assert before.volatility_pct is None  # no Holdings/MarketPrice yet

    account.current_balance = 1000
    _add_holding(db_session, account, "AAPL", 1000)
    _add_prices(db_session, "AAPL", date.today() - timedelta(days=100), n=100)
    db_session.commit()

    after = build_risk_metrics(db_session, lookback_days=30)
    assert after.volatility_pct is not None and after.volatility_pct > 0
    # Backtest data appearing must not move Sharpe -- it's computed purely
    # from the real BalanceSnapshot series, untouched by this change.
    assert after.sharpe_ratio == before.sharpe_ratio


def test_backtest_excludes_tickers_with_no_price_history(db_session, account):
    account.current_balance = 1500
    _add_holding(db_session, account, "AAPL", 1000)
    _add_holding(db_session, account, "NOPRICE", 500)
    _add_prices(db_session, "AAPL", date.today() - timedelta(days=100), n=100)
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=365)

    assert data.var_excluded_tickers == ["NOPRICE"]
    # Coverage = priceable (AAPL, $1000) / total ($1500)
    assert data.var_coverage_pct == pytest.approx(1000 / 1500 * 100, abs=0.1)
    assert data.var_horizons  # still populates from the priceable subset
    assert data.volatility_pct is not None


def test_var_gates_each_horizon_independently(db_session, account):
    # 40 raw days -> 39 daily returns: enough for 1d/5d (>=30 obs after
    # rolling) but not 30d (39-29=10 obs, below MIN_BACKTEST_DATA_POINTS).
    account.current_balance = 1000
    _add_holding(db_session, account, "AAPL", 1000)
    _add_prices(db_session, "AAPL", date.today() - timedelta(days=40), n=40)
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=365)

    days_present = {h.days for h in data.var_horizons}
    assert days_present == {1, 5}
    assert 30 not in days_present
    # Volatility uses the same overall gate as VaR (39 obs >= 30), so it
    # still populates even though the 30d VaR horizon specifically doesn't.
    assert data.volatility_pct is not None


def test_backtest_insufficient_history_returns_empty(db_session, account):
    account.current_balance = 1000
    _add_holding(db_session, account, "AAPL", 1000)
    _add_prices(db_session, "AAPL", date.today() - timedelta(days=10), n=10)
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=365)

    assert data.var_horizons == []
    assert data.var_data_points < MIN_BACKTEST_DATA_POINTS
    assert data.volatility_pct is None


def test_backtest_log_returns_keep_equity_weekend_move(db_session):
    # Union of BTC (has Saturday) and SPY (weekday only): Saturday is NaN for
    # SPY. Naive shift(1) makes Monday/SaturdayNaN = NaN, so SPY's Friday→Monday
    # move disappears and Monday is BTC-only. Previous-valid close must keep it.
    fri, sat, mon = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 5)
    db_session.add(MarketPrice(ticker="SPY", price_date=fri, close_price=100))
    db_session.add(MarketPrice(ticker="SPY", price_date=mon, close_price=102))
    db_session.add(MarketPrice(ticker="BTC", price_date=fri, close_price=10))
    db_session.add(MarketPrice(ticker="BTC", price_date=sat, close_price=10.5))
    db_session.add(MarketPrice(ticker="BTC", price_date=mon, close_price=10.8))
    db_session.commit()

    series = _backtest_portfolio_log_returns(
        db_session, ["SPY", "BTC"], {"SPY": 0.5, "BTC": 0.5}, fri, mon,
    )

    assert mon in list(series.index)
    expected_mon = 0.5 * np.log(102 / 100) + 0.5 * np.log(10.8 / 10.5)
    assert series.loc[mon] == pytest.approx(expected_mon)
    assert sat in list(series.index)
    assert series.loc[sat] == pytest.approx(np.log(10.5 / 10))
