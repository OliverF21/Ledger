# backend/tests/test_optimizer_constraints.py
"""
Constraint handling and the frontier sweep, exercised directly against the
solver helpers on synthetic returns. Kept separate from
test_optimization_service.py, which covers the DB-backed end-to-end path —
here the point is that a bound the user sets is actually enforced, which needs
controlled covariance rather than fixture prices.
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet

# See test_optimization_service.py: the import chain reaches app.security,
# which raises at import time without a key.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.services.optimization_service import (  # noqa: E402
    TRADING_DAYS_PER_YEAR,
    OptimizerConstraints,
    _bounds,
    _build_frontier,
    _random_scatter,
    _sector_constraint_defs,
    _solve,
)

TICKERS = ["VTI", "VOO", "AAPL", "NVDA", "BND", "SCHD"]
SECTORS = {
    "VTI": "Broad", "VOO": "Broad", "SCHD": "Broad",
    "AAPL": "Technology", "NVDA": "Technology",
    "BND": "Bonds",
}
RISK_FREE_PCT = 4.42
TOL = 1e-6


@pytest.fixture(scope="module")
def market():
    """Daily returns with deliberately spread means and vols, so a cap actually
    bites — with near-identical assets any weighting satisfies any bound and
    the assertions below would pass vacuously."""
    rng = np.random.default_rng(7)
    returns = rng.normal(
        loc=[0.0004, 0.00038, 0.0006, 0.0009, 0.0001, 0.0003],
        scale=[0.008, 0.0078, 0.014, 0.026, 0.003, 0.007],
        size=(400, len(TICKERS)),
    )
    return returns.mean(axis=0), np.cov(returns, rowvar=False)


def _neg_sharpe(mean_returns, cov):
    def objective(weights: np.ndarray) -> float:
        ret = float(np.dot(weights, mean_returns)) * TRADING_DAYS_PER_YEAR
        vol = float(np.sqrt(weights @ cov @ weights)) * np.sqrt(TRADING_DAYS_PER_YEAR)
        return 0.0 if vol == 0 else -(ret - RISK_FREE_PCT / 100) / vol
    return objective


@pytest.mark.parametrize("cap_pct", [100, 40, 25])
def test_position_cap_is_enforced(market, cap_pct):
    mean_returns, cov = market
    constraints = OptimizerConstraints(position_cap_pct=cap_pct)
    weights = _solve(_neg_sharpe(mean_returns, cov), _bounds(TICKERS, constraints), [])

    assert weights is not None
    assert weights.max() <= cap_pct / 100 + TOL
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)


def test_ticker_floor_overrides_the_global_cap(market):
    mean_returns, cov = market
    # BND is the worst Sharpe asset here, so an unconstrained solve drops it —
    # which is exactly what makes it a real test of the floor.
    constraints = OptimizerConstraints(
        position_cap_pct=40, ticker_bounds={"BND": (20.0, 35.0)}
    )
    weights = _solve(_neg_sharpe(mean_returns, cov), _bounds(TICKERS, constraints), [])

    assert weights is not None
    bnd = weights[TICKERS.index("BND")]
    assert bnd >= 0.20 - TOL
    assert bnd <= 0.35 + TOL


def test_sector_cap_is_enforced(market):
    mean_returns, cov = market
    constraints = OptimizerConstraints(
        position_cap_pct=100, sector_bounds={"Technology": (0.0, 15.0)}
    )
    weights = _solve(
        _neg_sharpe(mean_returns, cov),
        _bounds(TICKERS, constraints),
        _sector_constraint_defs(TICKERS, SECTORS, constraints),
    )

    assert weights is not None
    tech = weights[TICKERS.index("AAPL")] + weights[TICKERS.index("NVDA")]
    assert tech <= 0.15 + 1e-4


def test_infeasible_constraints_report_rather_than_guess(market):
    """Floors that can't coexist must come back as None so the caller can say
    so, not as a silently-renormalised answer that violates them."""
    mean_returns, cov = market
    constraints = OptimizerConstraints(
        position_cap_pct=100,
        sector_bounds={"Technology": (80.0, 100.0), "Bonds": (80.0, 100.0)},
    )
    weights = _solve(
        _neg_sharpe(mean_returns, cov),
        _bounds(TICKERS, constraints),
        _sector_constraint_defs(TICKERS, SECTORS, constraints),
    )
    assert weights is None


def test_frontier_is_sorted_and_monotone(market):
    mean_returns, cov = market
    constraints = OptimizerConstraints(position_cap_pct=40)
    frontier = _build_frontier(
        mean_returns, cov, _bounds(TICKERS, constraints), [], RISK_FREE_PCT
    )

    assert len(frontier) > 20
    vols = [p.volatility_pct for p in frontier]
    assert vols == sorted(vols)
    # Taking on more risk should buy more return along an efficient frontier.
    assert frontier[-1].return_pct > frontier[0].return_pct


def test_scatter_is_deterministic(market):
    """The cloud is seeded so it doesn't reshuffle every time a slider moves."""
    mean_returns, cov = market
    first = _random_scatter(mean_returns, cov, RISK_FREE_PCT)
    second = _random_scatter(mean_returns, cov, RISK_FREE_PCT)

    assert len(first) > 100
    assert [(p.volatility_pct, p.return_pct) for p in first] == [
        (p.volatility_pct, p.return_pct) for p in second
    ]
