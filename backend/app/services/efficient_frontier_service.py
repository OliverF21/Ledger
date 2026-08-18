"""
Efficient frontier as a swept set of (volatility, max achievable return)
points -- each point is an independent scipy SLSQP solve at a fixed target
volatility. Non-convergent points are dropped, not substituted with a
fallback (e.g. equal-weight), since a fallback point would misleadingly
suggest that risk/return combination is achievable when it isn't.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

TRADING_DAYS_PER_YEAR = 252
MAX_FRONTIER_POINTS = 20


def _min_max_volatility(mu, cov, bounds, sector_constraints):
    n = len(mu)
    sum_to_one = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
    constraints = [sum_to_one] + (sector_constraints or [])

    def vol(w):
        return np.sqrt(w @ cov @ w)

    initial = np.array([1.0 / n] * n)
    min_result = minimize(vol, initial, method="SLSQP", bounds=bounds, constraints=constraints)
    max_ret_result = minimize(lambda w: -(w @ mu), initial, method="SLSQP", bounds=bounds, constraints=constraints)
    if not min_result.success or not max_ret_result.success:
        return None, None
    return float(vol(min_result.x)), float(np.sqrt(max_ret_result.x @ cov @ max_ret_result.x))


def sweep_efficient_frontier(
    mu: np.ndarray, cov: np.ndarray, bounds: list[tuple[float, float]],
    sector_constraints: list[dict] | None, n_points: int = MAX_FRONTIER_POINTS,
) -> list[dict]:
    n = len(mu)
    sum_to_one = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
    base_constraints = [sum_to_one] + (sector_constraints or [])

    min_vol, max_vol = _min_max_volatility(mu, cov, bounds, sector_constraints)
    if min_vol is None:
        return []

    points = []
    for target_vol in np.linspace(min_vol, max_vol, n_points):
        vol_constraint = {"type": "eq", "fun": lambda w, tv=target_vol: np.sqrt(w @ cov @ w) - tv}
        result = minimize(
            lambda w: -(w @ mu), np.array([1.0 / n] * n), method="SLSQP",
            bounds=bounds, constraints=base_constraints + [vol_constraint],
        )
        if not result.success:
            continue  # drop, don't substitute -- see module docstring
        points.append({
            "volatility_pct": round(target_vol * 100, 3),
            "return_pct": round(float(result.x @ mu) * 100, 3),
        })
    return points
