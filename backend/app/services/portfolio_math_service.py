"""
Closed-form portfolio math (Ledoit-Wolf covariance shrinkage, Black-Litterman
market-implied prior/posterior) — deliberately NOT using pypfopt/cvxpy (see
docs/superpowers/specs/2026-08-17-portfolio-optimization-v2-design.md for
why). All of this is linear algebra, no solver needed; only the final
constrained portfolio solve (efficient_frontier_service.py,
optimization_service.py) needs scipy.optimize.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def ledoit_wolf_shrinkage(returns: np.ndarray) -> np.ndarray:
    """
    Ledoit-Wolf (2004) shrinkage toward a constant-correlation target.
    Returns an ANNUALIZED covariance matrix (matches CovarianceShrinkage's
    default behavior in the example script, and mean_returns' annualization
    elsewhere in this codebase).
    """
    t, n = returns.shape
    x = returns - returns.mean(axis=0)
    sample_cov = (x.T @ x) / t

    var = np.diag(sample_cov)
    std = np.sqrt(var)
    # Floor std before dividing: a zero-/near-zero-variance asset (constant,
    # stale, or halted price series) would otherwise make its row/column
    # 0/0 = NaN in `corr`, which propagates through the pooled `avg_corr`
    # scalar into every asset's entry of `target` — not just the degenerate
    # one. 1e-12 is many orders of magnitude below any realistic daily
    # return volatility, so this floor only activates for genuinely
    # zero/near-zero variance assets; `target`'s off-diagonal entries for
    # such an asset still work out to ~0 below (via the un-floored `std` in
    # the outer product), and its diagonal is still its true (zero)
    # variance via `np.fill_diagonal`.
    std_safe = np.maximum(std, 1e-12)
    corr = sample_cov / np.outer(std_safe, std_safe)
    avg_corr = (corr.sum() - n) / (n * (n - 1)) if n > 1 else 0.0
    target = avg_corr * np.outer(std, std)
    np.fill_diagonal(target, var)

    # Shrinkage intensity (Ledoit-Wolf's asymptotically optimal estimator,
    # simplified single-parameter form — see design doc for the full
    # derivation reference).
    y = x ** 2
    phi_mat = (y.T @ y) / t - sample_cov ** 2
    phi = phi_mat.sum()
    gamma = np.sum((target - sample_cov) ** 2)
    kappa = phi / gamma if gamma > 0 else 0.0
    shrinkage = max(0.0, min(1.0, kappa / t))

    shrunk = shrinkage * target + (1 - shrinkage) * sample_cov
    return shrunk * TRADING_DAYS_PER_YEAR


def market_implied_risk_aversion(benchmark_prices: pd.Series, risk_free_rate_pct: float) -> float:
    """δ = (annualized excess return) / (annualized variance) of the market
    proxy — the risk-aversion coefficient of an investor optimally holding
    exactly the market portfolio, per the standard reverse-optimization
    formula. Used both to build the Black-Litterman prior AND as the
    quadratic-utility objective's risk-aversion parameter."""
    daily_returns = benchmark_prices.pct_change().dropna()
    annual_return = daily_returns.mean() * TRADING_DAYS_PER_YEAR
    annual_var = daily_returns.var() * TRADING_DAYS_PER_YEAR
    return float((annual_return - risk_free_rate_pct / 100) / annual_var)
