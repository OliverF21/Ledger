# backend/tests/test_optimization_service.py
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from cryptography.fernet import Fernet

# optimization_service imports get_cached_risk_free_rate -> app_config ->
# app.security, which raises at import time if ENCRYPTION_KEY is unset. Match
# the same workaround used by other tests that transitively touch
# app.security (e.g. tests/test_risk_free_rate.py, tests/test_risk_service.py)
# so this file passes when run standalone, not just as part of the full suite.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Account, Base, Holding, Item, MarketPrice, Security, User  # noqa: E402
from app.services.optimization_service import build_optimization_suggestion  # noqa: E402


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'opt.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _setup_two_ticker_portfolio(db):
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db.add(item)
    db.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment", current_balance=Decimal("2000"))
    db.add(account)
    db.flush()

    sec_a = Security(plaid_security_id="sec-A", ticker_symbol="TICKA", type="equity")
    sec_b = Security(plaid_security_id="sec-B", ticker_symbol="TICKB", type="equity")
    db.add_all([sec_a, sec_b])
    db.flush()

    # Equal-dollar starting weights: 50/50.
    db.add(Holding(account_id=account.id, security_id=sec_a.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))
    db.add(Holding(account_id=account.id, security_id=sec_b.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))

    # TICKA: steady uptrend, low volatility. TICKB: flat with noise. A high-Sharpe
    # optimizer should shift weight toward TICKA relative to the 50/50 start.
    start = date.today() - timedelta(days=60)
    a_prices = [100 + i * 0.5 for i in range(60)]
    b_prices = [100 + (5 if i % 2 == 0 else -5) for i in range(60)]
    for i in range(60):
        day = start + timedelta(days=i)
        db.add(MarketPrice(ticker="TICKA", price_date=day, close_price=Decimal(str(a_prices[i]))))
        db.add(MarketPrice(ticker="TICKB", price_date=day, close_price=Decimal(str(b_prices[i]))))
    db.commit()
    return account


def test_optimization_shifts_weight_toward_higher_sharpe_asset(db_session):
    _setup_two_ticker_portfolio(db_session)

    data = build_optimization_suggestion(db_session, lookback_days=90)

    assert not data.insufficient_data
    assert len(data.tickers) == 2
    weight_by_ticker = {t.ticker: t for t in data.tickers}
    assert weight_by_ticker["TICKA"].current_weight_pct == pytest.approx(50.0, abs=0.5)
    assert weight_by_ticker["TICKB"].current_weight_pct == pytest.approx(50.0, abs=0.5)
    # TICKA is a steady uptrend (high Sharpe), TICKB is flat/noisy (near-zero
    # Sharpe) -> the optimizer should suggest materially more than 50% in TICKA.
    assert weight_by_ticker["TICKA"].suggested_weight_pct > 60.0

    weights_sum = sum(t.suggested_weight_pct for t in data.tickers)
    assert weights_sum == pytest.approx(100.0, abs=0.1)
    for t in data.tickers:
        assert 0.0 <= t.suggested_weight_pct <= 100.0

    assert data.suggested_sharpe is not None and data.current_sharpe is not None
    assert data.suggested_sharpe >= data.current_sharpe - 0.01  # optimizer must not do worse


def test_optimization_drops_unpriceable_ticker_and_uses_remaining(db_session):
    # Three-ticker portfolio where TICKC has a holding but zero MarketPrice
    # rows (e.g. yfinance couldn't resolve it). The optimizer should drop
    # TICKC and still produce a valid suggestion over TICKA/TICKB rather than
    # reporting insufficient_data for the whole book.
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment", current_balance=Decimal("3000"))
    db_session.add(account)
    db_session.flush()

    sec_a = Security(plaid_security_id="sec-A", ticker_symbol="TICKA", type="equity")
    sec_b = Security(plaid_security_id="sec-B", ticker_symbol="TICKB", type="equity")
    sec_c = Security(plaid_security_id="sec-C", ticker_symbol="TICKC", type="equity")
    db_session.add_all([sec_a, sec_b, sec_c])
    db_session.flush()

    db_session.add(Holding(account_id=account.id, security_id=sec_a.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))
    db_session.add(Holding(account_id=account.id, security_id=sec_b.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))
    # TICKC is held but has NO MarketPrice rows at all -- unresolvable ticker.
    db_session.add(Holding(account_id=account.id, security_id=sec_c.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))

    start = date.today() - timedelta(days=60)
    a_prices = [100 + i * 0.5 for i in range(60)]
    b_prices = [100 + (5 if i % 2 == 0 else -5) for i in range(60)]
    for i in range(60):
        day = start + timedelta(days=i)
        db_session.add(MarketPrice(ticker="TICKA", price_date=day, close_price=Decimal(str(a_prices[i]))))
        db_session.add(MarketPrice(ticker="TICKB", price_date=day, close_price=Decimal(str(b_prices[i]))))
    db_session.commit()

    data = build_optimization_suggestion(db_session, lookback_days=90)

    assert not data.insufficient_data
    tickers_present = {t.ticker for t in data.tickers}
    assert tickers_present == {"TICKA", "TICKB"}


def test_optimization_insufficient_data_with_fewer_than_two_tickers(db_session):
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment")
    db_session.add(account)
    db_session.commit()

    data = build_optimization_suggestion(db_session, lookback_days=90)
    assert data.insufficient_data is True
    assert data.tickers == []
