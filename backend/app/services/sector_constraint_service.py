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

from app.models import SectorConstraint, TickerClassification

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

    return lower, upper, clip_log
