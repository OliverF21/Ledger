"""Tests for the compute_lookback_days helper in backfill_transfer_matches.py."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Transaction
from backfill_transfer_matches import compute_lookback_days


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_computes_days_since_earliest_transaction(db):
    db.add(Transaction(account_id=1, merchant="Test", amount=10.0, date=date(2024, 1, 15), removed=False))
    db.commit()

    days = compute_lookback_days(db, today=date(2026, 8, 28))

    assert days == (date(2026, 8, 28) - date(2024, 1, 15)).days + 1


def test_ignores_removed_transactions_for_earliest_date(db):
    db.add_all([
        Transaction(account_id=1, merchant="Removed", amount=10.0, date=date(2020, 1, 1), removed=True),
        Transaction(account_id=1, merchant="Kept", amount=10.0, date=date(2025, 1, 1), removed=False),
    ])
    db.commit()

    days = compute_lookback_days(db, today=date(2026, 8, 28))

    assert days == (date(2026, 8, 28) - date(2025, 1, 1)).days + 1


def test_returns_zero_when_no_transactions(db):
    days = compute_lookback_days(db, today=date(2026, 8, 28))
    assert days == 0
