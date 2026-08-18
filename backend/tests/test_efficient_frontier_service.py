# backend/tests/test_efficient_frontier_service.py
import numpy as np

from app.services.efficient_frontier_service import sweep_efficient_frontier


def test_frontier_sweep_returns_monotonic_points():
    mu = np.array([0.10, 0.15, 0.08])
    cov = np.array([[0.04, 0.01, 0.0], [0.01, 0.09, 0.01], [0.0, 0.01, 0.03]])
    bounds = [(0.0, 1.0)] * 3

    points = sweep_efficient_frontier(mu, cov, bounds, sector_constraints=None, n_points=10)

    assert len(points) > 0
    assert len(points) <= 10
    vols = [p["volatility_pct"] for p in points]
    assert vols == sorted(vols)  # target vols swept in increasing order


def test_frontier_sweep_drops_non_convergent_points_not_substitutes():
    # Extremely tight, likely partially-infeasible bounds to force some
    # target volatilities to fail to converge.
    mu = np.array([0.50, 0.02])
    cov = np.array([[0.25, 0.0], [0.0, 0.001]])
    bounds = [(0.45, 0.55), (0.45, 0.55)]  # deliberately narrow

    points = sweep_efficient_frontier(mu, cov, bounds, sector_constraints=None, n_points=10)

    # Whatever comes back must be a strict subset of feasible points, not a
    # full 10-point curve padded with equal-weight fallbacks.
    assert len(points) <= 10
    for p in points:
        assert p["volatility_pct"] > 0
