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
    assert data.volatility_pct is not None and data.volatility_pct > 0
    assert data.var_95_pct is not None
    assert data.risk_free_rate_pct > 0  # falls back to DEFAULT_RISK_FREE_RATE_PCT


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
