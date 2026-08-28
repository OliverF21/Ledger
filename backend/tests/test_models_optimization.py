import os
from pathlib import Path

# optimization_service imports get_cached_risk_free_rate -> app_config ->
# app.security, which raises at import time if ENCRYPTION_KEY is unset. Match
# the same workaround used by other tests that transitively touch
# app.security.
import sys

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base,
    SectorConstraint,
    TickerClassification,
    TickerConstraint,
    User,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_models_opt.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_ticker_classification_round_trip(db_session):
    row = TickerClassification(
        ticker="VOO",
        asset_class="etf",
        sector_weights_json='{"technology": 0.32, "healthcare": 0.11}',
        market_cap_or_aum=450_000_000_000,
    )
    db_session.add(row)
    db_session.commit()
    fetched = db_session.query(TickerClassification).filter_by(ticker="VOO").one()
    assert fetched.asset_class == "etf"
    assert fetched.sync_error is None


def test_sector_constraint_unique_per_user_sector(db_session):
    db_session.add(
        SectorConstraint(user_id=1, sector="technology", floor_pct=5, cap_pct=35)
    )
    db_session.commit()
    dup = SectorConstraint(
        user_id=1, sector="technology", floor_pct=1, cap_pct=99
    )
    db_session.add(dup)
    with pytest.raises(Exception):
        db_session.commit()


def test_ticker_constraint_round_trip(db_session):
    db_session.add(TickerConstraint(user_id=1, ticker="VOO", floor_pct=5, cap_pct=100))
    db_session.commit()
    fetched = db_session.query(TickerConstraint).filter_by(ticker="VOO").one()
    assert float(fetched.floor_pct) == 5.0


def test_user_optimization_columns_default(db_session):
    user = db_session.query(User).filter_by(id=1).one()
    assert user.optimization_advanced_enabled is False
    assert float(user.optimization_position_cap_pct) == 10.0
    assert float(user.optimization_concentration_strength) == 0.5
