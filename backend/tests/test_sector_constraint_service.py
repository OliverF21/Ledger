from __future__ import annotations

import json

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, SectorConstraint, TickerClassification, User
from app.services.sector_constraint_service import build_sector_exposure_matrix, clip_sector_bounds


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_sector_constraint.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _classify(db_session, ticker, weights):
    db_session.add(TickerClassification(ticker=ticker, asset_class="etf", sector_weights_json=json.dumps(weights)))


def test_build_sector_exposure_matrix_shape_and_values(db_session):
    _classify(db_session, "AAPL", {"technology": 1.0})
    _classify(db_session, "VOO", {"technology": 0.3, "healthcare": 0.12})
    db_session.commit()

    matrix, sectors = build_sector_exposure_matrix(db_session, ["AAPL", "VOO"])

    assert "technology" in sectors and "healthcare" in sectors
    tech_col = sectors.index("technology")
    assert matrix[0, tech_col] == 1.0
    assert matrix[1, tech_col] == 0.3


def test_clip_sector_bounds_leaves_achievable_floor_untouched(db_session):
    _classify(db_session, "XLV", {"healthcare": 1.0})
    db_session.add(SectorConstraint(user_id=1, sector="healthcare", floor_pct=2.0, cap_pct=40.0))
    db_session.commit()

    matrix, sectors = build_sector_exposure_matrix(db_session, ["XLV"])
    lower, upper, clip_log = clip_sector_bounds(db_session, 1, sectors, matrix, position_cap=0.10)

    idx = sectors.index("healthcare")
    assert lower[idx] == 0.02  # 10% cap on a 100%-healthcare ticker easily clears a 2% floor
    assert clip_log == []


def test_clip_sector_bounds_clips_unreachable_floor(db_session):
    # Single ticker with only 17% exposure to "basicmaterials", capped at 10%
    # position size -> max achievable = 0.10 * 0.17 = 0.017, below a 2% floor.
    _classify(db_session, "SOMEETF", {"basicmaterials": 0.17, "technology": 0.83})
    db_session.add(SectorConstraint(user_id=1, sector="basicmaterials", floor_pct=2.0, cap_pct=40.0))
    db_session.commit()

    matrix, sectors = build_sector_exposure_matrix(db_session, ["SOMEETF"])
    lower, upper, clip_log = clip_sector_bounds(db_session, 1, sectors, matrix, position_cap=0.10)

    idx = sectors.index("basicmaterials")
    assert lower[idx] < 0.02
    assert lower[idx] == pytest.approx(0.017 * 0.95, rel=1e-6)  # safety margin
    assert len(clip_log) == 1
    assert clip_log[0]["sector"] == "basicmaterials"


def test_clip_sector_bounds_logs_constraint_on_sector_absent_from_matrix(db_session):
    # Only holding is 100% technology -- "utilities" never appears as a
    # column in the exposure matrix at all (0% achievable, no held ticker
    # has any exposure to it). A floor constraint on it is even more
    # unreachable than the in-matrix clip case, so it must still surface
    # in clip_log even though sector_names never contains "utilities" and
    # there's no lower/upper slot for it.
    _classify(db_session, "AAPL", {"technology": 1.0})
    db_session.add(SectorConstraint(user_id=1, sector="utilities", floor_pct=5.0, cap_pct=40.0))
    db_session.commit()

    matrix, sectors = build_sector_exposure_matrix(db_session, ["AAPL"])
    assert sectors == ["technology"]  # "utilities" never made it into the matrix

    lower, upper, clip_log = clip_sector_bounds(db_session, 1, sectors, matrix, position_cap=0.10)

    assert lower.shape == (1,)  # no bound-vector slot added for "utilities"
    assert upper.shape == (1,)
    assert len(clip_log) == 1
    assert clip_log[0]["sector"] == "utilities"
    assert clip_log[0]["requested_floor"] == 0.05
    assert clip_log[0]["clipped_to"] == 0.0
