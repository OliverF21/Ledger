"""
Efficient frontier as a swept set of (volatility, max achievable return)
points -- each point is an independent scipy SLSQP solve at a fixed target
volatility. Non-convergent points are dropped, not substituted with a
fallback (e.g. equal-weight), since a fallback point would misleadingly
suggest that risk/return combination is achievable when it isn't.

`mu`/`cov` are DAILY-scale (optimization_service.py passes mu_bl/sigma_bl,
its Black-Litterman posterior before any annualization). The solver has to
stay in that scale internally -- target_vol is swept and constrained
against `cov` directly, so annualizing it first would constrain against
the wrong-scale matrix. Only the OUTPUT points are annualized, right
before rounding, to match portfolio_stats()'s convention (in
price_matrix_service.py: return x TRADING_DAYS_PER_YEAR, volatility x
sqrt(TRADING_DAYS_PER_YEAR), 365 calendar days -- not 252 trading days,
so the two objective markers Investments.tsx plots alongside this curve
(both come from portfolio_stats) land on the same scale rather than
~19x/~365x off on the volatility/return axes respectively.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

TRADING_DAYS_PER_YEAR = 365
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
        annualized_vol = target_vol * np.sqrt(TRADING_DAYS_PER_YEAR)
        annualized_return = float(result.x @ mu) * TRADING_DAYS_PER_YEAR
        points.append({
            "volatility_pct": round(annualized_vol * 100, 3),
            "return_pct": round(annualized_return * 100, 3),
        })
    return points
