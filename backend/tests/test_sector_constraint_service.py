from __future__ import annotations

import json

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, SectorConstraint, TickerClassification, TickerConstraint, User
from app.services.sector_constraint_service import (
    build_sector_exposure_matrix,
    build_ticker_bounds,
    clip_sector_bounds,
    relax_position_cap_if_needed,
)


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


def test_relax_position_cap_when_too_few_holdings():
    # 5 holdings, 10% cap -> max 50%, can't reach sum=1. Must relax toward 1/n.
    effective_cap, log_entry = relax_position_cap_if_needed(n_tickers=5, requested_cap=0.10)
    assert effective_cap >= 1 / 5
    assert log_entry is not None
    assert log_entry["requested_cap"] == 0.10


def test_relax_position_cap_no_relax_when_feasible():
    effective_cap, log_entry = relax_position_cap_if_needed(n_tickers=30, requested_cap=0.10)
    assert effective_cap == 0.10
    assert log_entry is None


def test_relax_position_cap_returns_unchanged_for_zero_tickers():
    # No holdings at all -- nothing to relax the cap against (would be a
    # ZeroDivisionError in 1/n_tickers without the explicit guard). Should
    # be a no-op: pass the requested cap straight through, no log entry.
    effective_cap, log_entry = relax_position_cap_if_needed(n_tickers=0, requested_cap=0.10)
    assert effective_cap == 0.10
    assert log_entry is None


def test_relax_position_cap_clamps_to_full_allocation_for_single_holding():
    # 1 holding -> min_feasible_cap = (1/1)/0.95 ~= 1.0526, which exceeds
    # 100%. The relaxed cap must still clamp at 1.0 -- a position "cap"
    # above 100% is meaningless.
    effective_cap, log_entry = relax_position_cap_if_needed(n_tickers=1, requested_cap=0.5)
    assert effective_cap == 1.0
    assert log_entry == {"requested_cap": 0.5, "relaxed_to": 1.0, "reason": "too few holdings for cap"}


def test_build_ticker_bounds_ticker_cap_supersedes_position_cap(db_session):
    # A manually-set per-ticker cap ABOVE the global position cap must win --
    # a user who explicitly asks for "VOO up to 100%" should get 100%, not
    # have it silently re-clamped down to the 10% they set for everything
    # else. (Previously this WAS clamped to position_cap, meaning a manual
    # override above the global cap was accepted by the UI/API but had zero
    # effect on the actual solve.) The floor still applies normally; AAPL
    # (no constraint) still falls back to the global cap as its ceiling.
    db_session.add(TickerConstraint(user_id=1, ticker="VOO", floor_pct=5.0, cap_pct=100.0))
    db_session.commit()

    lower, upper = build_ticker_bounds(db_session, 1, ["VOO", "AAPL"], position_cap=0.10)

    assert lower[0] == 0.05  # VOO floor
    assert upper[0] == 1.0  # VOO's own cap supersedes the 10% position cap
    assert lower[1] == 0.0
    assert upper[1] == 0.10  # AAPL has no override, still bound by the position cap


def test_build_ticker_bounds_ignores_constraint_for_ticker_outside_universe(db_session):
    # A TickerConstraint on "TSLA" exists, but "TSLA" isn't in the tickers
    # being optimized over -- there's no bounds slot for it (arrays are
    # sized to len(tickers)), so it must have zero effect: no crash, no
    # misapplied bound on the one ticker that IS in the list.
    db_session.add(TickerConstraint(user_id=1, ticker="TSLA", floor_pct=20.0, cap_pct=100.0))
    db_session.commit()

    lower, upper = build_ticker_bounds(db_session, 1, ["AAPL"], position_cap=0.10)

    assert lower.shape == (1,)
    assert upper.shape == (1,)
    assert lower[0] == 0.0
    assert upper[0] == 0.10


def test_build_ticker_bounds_clamps_inverted_preexisting_row(db_session):
    # A row with floor_pct > cap_pct, constructed directly against the ORM to
    # bypass the API layer -- exactly how a row created BEFORE
    # routes/optimization_settings.py's floor<=cap validator existed (or one
    # written straight to SQLite) would look on disk today.
    #
    # Without the defensive clamp this produces bounds of (0.40, 0.02), and
    # scipy.optimize.minimize raises `ValueError: An upper bound is less than
    # the corresponding lower bound` -- killing the whole advanced-mode solve
    # over one malformed row. The clamp must degrade it to "cap only, no
    # floor" instead.
    db_session.add(TickerConstraint(user_id=1, ticker="BADROW", floor_pct=40.0, cap_pct=2.0))
    db_session.commit()

    lower, upper = build_ticker_bounds(db_session, 1, ["BADROW"], position_cap=0.50)

    assert lower[0] <= upper[0]
    assert upper[0] == 0.02  # the cap (the risk-limiting half) is what survives
    assert lower[0] == 0.02  # floor collapsed onto it rather than staying inverted

    # The bounds are directly scipy-usable, which is the whole point.
    from scipy.optimize import minimize
    result = minimize(
        lambda w: float(w @ w), np.array([0.02]), method="SLSQP",
        bounds=list(zip(lower, upper)),
    )  # must not raise ValueError
    assert result is not None


def test_build_ticker_bounds_applies_tighter_ticker_cap_below_position_cap(db_session):
    # The ticker's own cap_pct (3%) is tighter than the global position cap
    # (20%) -- it should bind directly, not get overridden by the wider
    # global cap. Covers the other direction of the cap_pct clamp from the
    # brief's own test, which only exercises cap_pct=100 always losing to
    # the (tighter) position cap.
    db_session.add(TickerConstraint(user_id=1, ticker="BOND", floor_pct=0.0, cap_pct=3.0))
    db_session.commit()

    lower, upper = build_ticker_bounds(db_session, 1, ["BOND"], position_cap=0.20)

    assert lower[0] == 0.0
    assert upper[0] == 0.03
