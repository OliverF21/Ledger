from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

# app.scheduler's sync_sector_data_job lazily imports app.database inside the
# function body, but other test files in this suite defensively set
# ENCRYPTION_KEY before importing anything that might transitively touch
# app.security (see test_market_data_scheduler.py, test_models_optimization.py)
# — match that convention here too.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Account, Base, Holding, Item, Security, TickerClassification, User  # noqa: E402
from app.scheduler import sync_sector_data_job  # noqa: E402
from app.sector_data_provider import TickerClassificationData  # noqa: E402
from app.services.sector_sync_service import sync_sector_classifications, tickers_needing_sector_sync  # noqa: E402


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sector_sync.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _held_security(db, ticker):
    item = Item(user_id=1, item_id=f"item-{ticker}", access_token_encrypted="x")
    db.add(item)
    db.flush()
    account = Account(item_id=item.id, plaid_account_id=f"acc-{ticker}", name="Brokerage", type="investment")
    db.add(account)
    security = Security(plaid_security_id=f"sec-{ticker}", ticker_symbol=ticker, type="equity")
    db.add(security)
    db.flush()
    db.add(Holding(account_id=account.id, security_id=security.id, quantity=Decimal("1"), institution_value=Decimal("100")))
    db.commit()


def test_tickers_needing_sector_sync_includes_held_tickers_without_a_row(db_session):
    _held_security(db_session, "AAPL")
    assert "AAPL" in tickers_needing_sector_sync(db_session)


def test_tickers_needing_sector_sync_excludes_recently_synced(db_session):
    _held_security(db_session, "AAPL")
    db_session.add(TickerClassification(ticker="AAPL", asset_class="equity", last_synced_at=datetime.utcnow()))
    db_session.commit()
    assert "AAPL" not in tickers_needing_sector_sync(db_session)


def test_tickers_needing_sector_sync_includes_stale_row(db_session):
    _held_security(db_session, "AAPL")
    db_session.add(TickerClassification(
        ticker="AAPL", asset_class="equity",
        last_synced_at=datetime.utcnow() - timedelta(days=30),
    ))
    db_session.commit()
    assert "AAPL" in tickers_needing_sector_sync(db_session)


@patch("app.services.sector_sync_service.fetch_ticker_classification")
def test_sync_upserts_and_counts_errors_non_fatally(mock_fetch, db_session):
    _held_security(db_session, "AAPL")
    _held_security(db_session, "BADTICKER")

    def side_effect(ticker):
        if ticker == "BADTICKER":
            return TickerClassificationData(asset_class="unknown", error="No data found")
        return TickerClassificationData(asset_class="equity", sector_weights={"technology": 1.0}, market_cap_or_aum=1e12)

    mock_fetch.side_effect = side_effect
    result = sync_sector_classifications(db_session)

    assert result["tickers_synced"] == 2
    assert result["errors"] == 1
    row = db_session.query(TickerClassification).filter_by(ticker="AAPL").one()
    assert row.asset_class == "equity"
    bad = db_session.query(TickerClassification).filter_by(ticker="BADTICKER").one()
    assert bad.sync_error == "No data found"


def test_sync_sector_data_job_calls_sync_sector_classifications(monkeypatch):
    import app.services.sector_sync_service as sector_sync_module

    sync_mock = MagicMock(return_value={"tickers_synced": 3, "errors": 1})
    monkeypatch.setattr(sector_sync_module, "sync_sector_classifications", sync_mock)

    sync_sector_data_job()

    sync_mock.assert_called_once()


def test_sync_sector_data_job_swallows_exceptions(monkeypatch):
    import app.services.sector_sync_service as sector_sync_module

    def _raise(db):
        raise RuntimeError("boom")

    monkeypatch.setattr(sector_sync_module, "sync_sector_classifications", _raise)

    sync_sector_data_job()  # must not raise
