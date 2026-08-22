"""
Builds the tickers x sectors exposure matrix from cached TickerClassification
rows, and turns user SectorConstraint rows into scipy-ready lower/upper
bound vectors -- auto-clipping any floor that's mathematically unreachable
given the position cap, per the feasibility bug found and fixed in
example_portfolio_optimization.py. See design doc for the derivation.
"""
from __future__ import annotations

import json

import numpy as np
from sqlalchemy.orm import Session

from app.models import SectorConstraint, TickerClassification, TickerConstraint

SAFETY_MARGIN = 0.95


def build_sector_exposure_matrix(db: Session, tickers: list[str]) -> tuple[np.ndarray, list[str]]:
    rows = db.query(TickerClassification).filter(TickerClassification.ticker.in_(tickers)).all()
    weights_by_ticker = {
        r.ticker: json.loads(r.sector_weights_json) if r.sector_weights_json else {}
        for r in rows
    }
    sector_names = sorted({s for w in weights_by_ticker.values() for s in w})
    matrix = np.zeros((len(tickers), len(sector_names)))
    for i, ticker in enumerate(tickers):
        for sector, frac in weights_by_ticker.get(ticker, {}).items():
            j = sector_names.index(sector)
            matrix[i, j] = frac
    return matrix, sector_names


def clip_sector_bounds(
    db: Session, user_id: int, sector_names: list[str], exposure_matrix: np.ndarray, position_cap: float
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    n_sectors = len(sector_names)
    lower = np.zeros(n_sectors)
    upper = np.ones(n_sectors)
    clip_log: list[dict] = []

    constraints = {
        c.sector: c
        for c in db.query(SectorConstraint).filter(SectorConstraint.user_id == user_id).all()
    }
    max_achievable = (exposure_matrix * position_cap).sum(axis=0)

    for j, sector in enumerate(sector_names):
        constraint = constraints.get(sector)
        if constraint is None:
            continue
        requested_floor = float(constraint.floor_pct) / 100
        requested_cap = float(constraint.cap_pct) / 100
        clip_target = max_achievable[j] * SAFETY_MARGIN
        if requested_floor > clip_target:
            lower[j] = clip_target
            clip_log.append({"sector": sector, "requested_floor": requested_floor, "clipped_to": clip_target})
        else:
            lower[j] = requested_floor
        upper[j] = requested_cap

    # Sectors with a constraint but no column in the exposure matrix (no
    # held/classified ticker has any exposure to them at all) get no
    # lower/upper slot -- there's nothing to clip in the bound vectors --
    # but a requested floor on one is 0% achievable, which is *more*
    # unreachable than the in-matrix clip case above. Log it for the same
    # UI-transparency reason, so an explicit floor preference doesn't
    # silently vanish just because the sector never made it into
    # sector_names.
    for sector, constraint in constraints.items():
        if sector in sector_names:
            continue
        requested_floor = float(constraint.floor_pct) / 100
        if requested_floor > 0:
            clip_log.append({"sector": sector, "requested_floor": requested_floor, "clipped_to": 0.0})

    return lower, upper, clip_log


def relax_position_cap_if_needed(n_tickers: int, requested_cap: float) -> tuple[float, dict | None]:
    """If n_tickers * requested_cap < 1.0, sum(weights)=1 is unreachable --
    relax the cap toward 1/n with the same safety-margin philosophy as
    clip_sector_bounds, rather than letting the solve fail outright."""
    if n_tickers == 0:
        return requested_cap, None
    min_feasible_cap = (1.0 / n_tickers) / SAFETY_MARGIN
    if requested_cap >= min_feasible_cap:
        return requested_cap, None
    effective_cap = min(1.0, min_feasible_cap)
    return effective_cap, {"requested_cap": requested_cap, "relaxed_to": effective_cap, "reason": "too few holdings for cap"}


def build_ticker_bounds(
    db: Session, user_id: int, tickers: list[str], position_cap: float
) -> tuple[np.ndarray, np.ndarray]:
    """Per-ticker (lower, upper) bounds: the global position cap by default,
    or a user-set TickerConstraint's own (floor_pct, cap_pct) verbatim when
    one exists for that ticker -- an explicit per-ticker override supersedes
    the global default entirely rather than being intersected with it, so a
    user who deliberately sets e.g. 'VOO up to 25%' gets 25%, not silently
    re-clamped down to a 10% global position cap they set for everything
    else. (Previously cap_pct WAS clamped to position_cap, which meant a
    manual per-ticker cap above the global cap was accepted by the UI/API
    but had zero effect on the actual solve -- silently ignored, with
    nothing surfaced anywhere to explain why.) An inverted row (floor_pct >
    cap_pct) is defensively clamped down to its own cap, degrading to "cap
    only, no floor" rather than handing scipy an inverted bound -- see the
    comment at that clamp below. A TickerConstraint whose ticker isn't in
    `tickers` (e.g. a stale constraint on a ticker no longer in the
    candidate universe) has no bound-vector slot to occupy and is filtered
    out at the query level -- it's simply not applicable to this run, not a
    clip worth logging (unlike clip_sector_bounds's sector case, this
    function has no log channel in its return signature)."""
    constraints = {
        c.ticker: c
        for c in db.query(TickerConstraint).filter(TickerConstraint.user_id == user_id, TickerConstraint.ticker.in_(tickers)).all()
    }
    lower = np.zeros(len(tickers))
    upper = np.full(len(tickers), position_cap)
    for i, ticker in enumerate(tickers):
        constraint = constraints.get(ticker)
        if constraint is None:
            continue
        lower[i] = float(constraint.floor_pct) / 100
        upper[i] = float(constraint.cap_pct) / 100
        # Defensive clamp against an inverted row (floor_pct > cap_pct).
        # routes/optimization_settings.py rejects such a pair with a 422 at
        # write time, but that only protects rows created FROM NOW ON -- a
        # row already sitting in a user's DB from before that validation
        # existed, or one written straight to SQLite, still reaches here.
        # scipy.optimize.minimize raises `ValueError: An upper bound is less
        # than the corresponding lower bound` on an inverted `bounds` entry,
        # which would take out the entire advanced-mode solve (and, via an
        # uncaught 500, the whole Investments page) over one malformed row.
        # Collapsing the floor onto the cap degrades that row to "cap only,
        # no floor" -- the conservative reading, since the cap is the
        # risk-limiting half of the pair.
        lower[i] = min(lower[i], upper[i])
    return lower, upper
