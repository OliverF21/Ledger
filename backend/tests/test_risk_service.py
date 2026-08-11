# backend/tests/test_risk_service.py
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

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

from app.models import Account, BalanceSnapshot, Base, Item, MarketPrice, User  # noqa: E402
from app.services.risk_service import build_risk_metrics  # noqa: E402


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
    assert data.var_95_pct is None
    assert data.var_99_pct is None
    assert data.risk_free_rate_pct > 0  # falls back to DEFAULT_RISK_FREE_RATE_PCT


def test_annualized_metrics_populate_past_min_points_floor(db_session, account):
    # 25 daily snapshots (above MIN_ANNUALIZED_METRICS_POINTS=21) with mild
    # noise so volatility/VaR are well-defined. Calendar span is only 24 days,
    # so CAGR/Sharpe stay withheld (need MIN_CAGR_CALENDAR_DAYS=90).
    d0 = date.today() - timedelta(days=24)
    values = [100, 101, 100, 102, 103, 102, 104, 105, 104, 106, 107, 106, 108,
              109, 108, 110, 111, 110, 112, 113, 112, 114, 115, 114, 116]
    for i, v in enumerate(values):
        db_session.add(BalanceSnapshot(account_id=account.id, balance=v, snapshot_date=d0 + timedelta(days=i)))
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=30)

    assert data.data_points == 25
    assert data.effective_days == 24
    assert data.series_start == d0.isoformat()
    assert data.volatility_pct is not None and data.volatility_pct > 0
    assert data.var_95_pct is not None
    assert data.var_99_pct is not None
    assert data.cagr_pct is None
    assert data.sharpe_ratio is None
    assert data.twr_pct is not None and data.twr_pct > 0


def test_sharpe_uses_cagr_not_arithmetic_mean(db_session, account):
    """Sharpe must match (CAGR − rf) / vol — not arithmetic mean×365."""
    # 100 calendar days with noisy upward drift so vol > 0.
    d0 = date.today() - timedelta(days=99)
    values = []
    v = 100.0
    for i in range(100):
        values.append(round(v, 4))
        # Alternate up/down around a positive drift so stddev is material.
        shock = 0.012 if i % 2 == 0 else -0.008
        v *= 1.0 + shock
    for i, bal in enumerate(values):
        db_session.add(
            BalanceSnapshot(account_id=account.id, balance=Decimal(str(bal)), snapshot_date=d0 + timedelta(days=i))
        )
    db_session.commit()

    data = build_risk_metrics(db_session, lookback_days=120)

    assert data.effective_days == 99
    assert data.cagr_pct is not None
    assert data.volatility_pct is not None and data.volatility_pct > 0
    assert data.sharpe_ratio is not None
    expected = (data.cagr_pct / 100 - data.risk_free_rate_pct / 100) / (data.volatility_pct / 100)
    assert data.sharpe_ratio == pytest.approx(expected, abs=0.02)
    # Period TWR and CAGR must describe the same series.
    assert data.twr_pct is not None
    total_growth = 1 + data.twr_pct / 100
    implied_cagr = (total_growth ** (365.0 / data.effective_days) - 1) * 100
    assert data.cagr_pct == pytest.approx(implied_cagr, abs=0.05)


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
