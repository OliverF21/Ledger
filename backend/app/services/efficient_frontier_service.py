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
RANDOM_PORTFOLIO_SAMPLES = 1500


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


def sample_random_portfolios(
    mu: np.ndarray, cov: np.ndarray, risk_free_rate_pct: float, n_samples: int = RANDOM_PORTFOLIO_SAMPLES,
) -> list[dict]:
    """Random (volatility, return, sharpe) cloud for the frontier chart's
    backdrop -- ported from example_portfolio_optimization.py's Dirichlet-
    sampled visualization (the original prototype this whole engine was
    built from). Purely illustrative: unlike sweep_efficient_frontier, this
    ignores bounds/sector_constraints entirely (pure sum-to-1, no-short
    simplex sample), because the point is to show how much of the
    mathematically-reachable universe the position cap and sector/ticker
    constraints cut away -- applying those same bounds here would make the
    cloud a strict subset of the frontier curve instead of a backdrop
    around it.

    Blends two Dirichlet concentrations, matching the original script:
    alpha=1 (uniform over the simplex, dense in the "middle" -- balanced
    portfolios) and alpha=0.2 (concentrated near the simplex's corners/edges
    -- concentrated few-asset portfolios). alpha=1 alone under-samples the
    corners, leaving the cloud visibly empty near each single-asset extreme.

    `mu`/`cov` are DAILY-scale, same convention as sweep_efficient_frontier
    above (see that function's module docstring) -- annualized here before
    rounding, for the same reason.

    n_samples defaults to 1500 (750 from each Dirichlet blend), not the
    original script's 12,000: that figure was sized for a static matplotlib
    PNG, not a live JSON response rendered as an interactive DOM/SVG
    scatter -- 1500 points is still visually a dense cloud while keeping
    the response payload and render cost reasonable.
    """
    n = len(mu)
    half = max(1, n_samples // 2)
    rng = np.random.default_rng()
    w = np.vstack([
        rng.dirichlet(np.ones(n), half),
        rng.dirichlet(np.full(n, 0.2), half),
    ])
    rets = (w @ mu) * TRADING_DAYS_PER_YEAR
    vols = np.sqrt(np.einsum("ij,jk,ik->i", w, cov, w)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpes = np.where(vols > 0, (rets - risk_free_rate_pct / 100) / vols, 0.0)
    return [
        {"volatility_pct": round(float(v) * 100, 3), "return_pct": round(float(r) * 100, 3), "sharpe": round(float(s), 3)}
        for v, r, s in zip(vols, rets, sharpes)
    ]
