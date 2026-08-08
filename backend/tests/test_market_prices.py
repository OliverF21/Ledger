from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Base, MarketPrice


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'market_prices.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_insert_and_query_market_price(db_session):
    db_session.add(MarketPrice(ticker="AAPL", price_date=date(2026, 1, 2), close_price=Decimal("192.53")))
    db_session.add(MarketPrice(ticker="AAPL", price_date=date(2026, 1, 3), close_price=Decimal("193.10")))
    db_session.commit()

    rows = db_session.query(MarketPrice).filter(MarketPrice.ticker == "AAPL").order_by(MarketPrice.price_date).all()
    assert [r.price_date for r in rows] == [date(2026, 1, 2), date(2026, 1, 3)]
    assert rows[0].close_price == Decimal("192.53")


def test_duplicate_ticker_date_rejected(db_session):
    db_session.add(MarketPrice(ticker="SPY", price_date=date(2026, 1, 2), close_price=Decimal("470.00")))
    db_session.commit()

    db_session.add(MarketPrice(ticker="SPY", price_date=date(2026, 1, 2), close_price=Decimal("471.00")))
    with pytest.raises(IntegrityError):
        db_session.commit()
