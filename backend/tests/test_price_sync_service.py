from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Account, Base, Holding, Item, MarketPrice, Security, User


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'price_sync.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _held_security(db, ticker="AAPL"):
    item = Item(user_id=1, item_id=f"item-{ticker}", access_token_encrypted="x")
    db.add(item)
    db.flush()
    account = Account(item_id=item.id, plaid_account_id=f"acc-{ticker}", name="Brokerage", type="investment")
    db.add(account)
    security = Security(plaid_security_id=f"sec-{ticker}", ticker_symbol=ticker, type="equity")
    db.add(security)
    db.flush()
    db.add(Holding(account_id=account.id, security_id=security.id, quantity=Decimal("10")))
    db.commit()


def test_tickers_needing_sync_includes_held_and_benchmarks(db_session):
    from app.services.price_sync_service import BENCHMARK_TICKERS, tickers_needing_sync

    _held_security(db_session, "AAPL")
    tickers = tickers_needing_sync(db_session)

    assert "AAPL" in tickers
    for benchmark in BENCHMARK_TICKERS:
        assert benchmark in tickers


def test_sync_market_prices_upserts_rows_and_skips_duplicates(db_session, monkeypatch):
    from app.services import price_sync_service

    _held_security(db_session, "AAPL")

    fake_rows = {
        "AAPL": [(date(2026, 1, 2), Decimal("192.53")), (date(2026, 1, 3), Decimal("193.10"))],
        "SPY": [(date(2026, 1, 2), Decimal("470.10"))],
        "BTC-USD": [(date(2026, 1, 2), Decimal("42000.00"))],
    }
    monkeypatch.setattr(price_sync_service, "fetch_daily_closes", lambda tickers, start, end: fake_rows)

    stats = price_sync_service.sync_market_prices(db_session)
    assert stats["rows_upserted"] == 4

    # Second call: fetch_daily_closes still returns the same rows (as if
    # yfinance re-served them), but sync_market_prices must not re-insert
    # dates already stored — this asserts the ticker's cutoff filtering, not
    # a DB-level unique-constraint catch.
    stats2 = price_sync_service.sync_market_prices(db_session)
    assert stats2["rows_upserted"] == 0
    assert db_session.query(MarketPrice).filter(MarketPrice.ticker == "AAPL").count() == 2
