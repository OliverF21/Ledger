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


def market_implied_prior(cov: np.ndarray, market_weights: np.ndarray, delta: float) -> np.ndarray:
    """π = δ·Σ·w_mkt — the reverse-optimized equilibrium return vector that
    makes market_weights the mean-variance-optimal (tangency) portfolio for
    (π, Σ, δ). market_weights must be a market-cap/AUM-weighted vector over
    the SAME assets as cov's rows/columns, summing to 1."""
    return delta * cov @ market_weights


def idzorek_omega(view_confidences: list[float], P: np.ndarray, tau: float, cov: np.ndarray) -> np.ndarray:
    """
    Idzorek's method: converts intuitive 0-1 confidence percentages into
    the view-uncertainty (Ω) diagonal matrix, rather than requiring the
    caller to construct Ω by hand. confidence=1 -> near-zero uncertainty
    (full trust in the view); confidence->0 -> uncertainty blows up,
    pulling the posterior back toward the prior.
    """
    k = P.shape[0]
    omega = np.zeros((k, k))
    tau_cov = tau * cov
    for i in range(k):
        p_i = P[i]
        view_variance_at_100pct_confidence = float(p_i @ tau_cov @ p_i)
        confidence = max(1e-6, min(1.0 - 1e-6, view_confidences[i]))
        # Idzorek's closed-form: uncertainty scales as (1/confidence - 1)
        # times the tau-scaled prior variance of the view portfolio.
        raw_omega_ii = view_variance_at_100pct_confidence * (1.0 / confidence - 1.0)
        # Floor at a tiny epsilon: view_variance_at_100pct_confidence (and
        # therefore raw_omega_ii) is exactly 0.0 whenever P's row is all
        # zero, or whenever the view references only a zero-variance asset
        # -- not just hypothetically: ledoit_wolf_shrinkage explicitly
        # supports zero-variance assets (stale/halted/constant price
        # series) as a first-class input elsewhere in this pipeline, and
        # leaves their row/column in cov exactly zero. Without this floor,
        # omega would be exactly singular and black_litterman_posterior's
        # np.linalg.inv(omega) would raise LinAlgError. 1e-10 is many
        # orders of magnitude below any realistic tau-scaled view variance
        # (the values here run ~1e-3 or larger), so it never perturbs a
        # normal view, while staying far above float64's precision floor
        # so its reciprocal (taken by black_litterman_posterior) stays a
        # large-but-finite, numerically well-behaved number rather than
        # something that risks overflow or a badly ill-conditioned inverse.
        omega[i, i] = max(raw_omega_ii, 1e-10)
    return omega


GAMMA_SHARPE_SCALE = 2.0       # calibrated so strength=1.0 gives a visible
GAMMA_UTILITY_SCALE = 0.3      # but not dominant pull toward diversification
                                # on each objective's own natural scale
                                # (Sharpe ~O(0.1-3), utility ~O(0.01-0.5)).


def concentration_gammas(strength: float) -> tuple[float, float]:
    """Maps the single user-facing 0-1 'diversification strength' slider to
    two independently-scaled gamma values, one per objective -- the two
    objectives have different natural magnitudes, so one raw gamma would
    mean very different things to each (see design doc, gamma scale
    mismatch section)."""
    strength = max(0.0, min(1.0, strength))
    return strength * GAMMA_SHARPE_SCALE, strength * GAMMA_UTILITY_SCALE


def black_litterman_posterior(
    cov: np.ndarray, pi: np.ndarray, P: np.ndarray, Q: np.ndarray, omega: np.ndarray, tau: float = 0.05
) -> tuple[np.ndarray, np.ndarray]:
    """
    Standard Black-Litterman posterior (He & Litterman 1999 formulation).

    Treats the equilibrium prior π and the views Q as two independent noisy
    observations of the same unknown mean-return vector, and combines them
    by precision (inverse-covariance) weighting:

      M    = (τΣ)⁻¹ + PᵀΩ⁻¹P            posterior precision of the mean
      μ_BL = M⁻¹ [(τΣ)⁻¹π + PᵀΩ⁻¹Q]     precision-weighted blend of π and Q
      Σ_BL = Σ + M⁻¹                     asset covariance + mean uncertainty

    Each source is weighted by its own precision, so μ_BL slides between the
    two ends: as Ω → ∞ (no confidence in the views) PᵀΩ⁻¹P → 0 and μ_BL → π,
    the pure equilibrium prior; as Ω → 0 (full confidence) the view terms
    dominate and μ_BL is pulled to satisfy Pμ = Q.

    M⁻¹ is the posterior covariance OF THE ESTIMATED MEAN, not of returns,
    which is why Σ_BL adds it to Σ rather than replacing Σ: an investor
    holding this portfolio bears both the assets' own return variance and
    the residual uncertainty about where their mean actually sits.

    Args:
      cov:   (n,n) asset return covariance Σ.
      pi:    (n,)  equilibrium prior returns, e.g. from market_implied_prior.
      P:     (k,n) view pick matrix -- row i selects the assets view i is about.
      Q:     (k,)  the views' asserted returns.
      omega: (k,k) view uncertainty Ω, e.g. from idzorek_omega.
      tau:   scalar scaling the prior's uncertainty relative to Σ.

    Returns (mu_bl, sigma_bl) as an (n,) vector and an (n,n) matrix.

    Raises np.linalg.LinAlgError if `tau * cov` or `omega` is singular --
    notably when cov contains a zero-variance asset, which forces that whole
    row/column to zero. Callers are expected to floor the covariance diagonal
    first; optimization_service.build_optimization_suggestion does exactly
    that before every call here.
    """
    tau_cov_inv = np.linalg.inv(tau * cov)
    omega_inv = np.linalg.inv(omega)

    posterior_precision = tau_cov_inv + P.T @ omega_inv @ P
    posterior_cov_of_mean = np.linalg.inv(posterior_precision)

    mu_bl = posterior_cov_of_mean @ (tau_cov_inv @ pi + P.T @ omega_inv @ Q)
    sigma_bl = cov + posterior_cov_of_mean
    return mu_bl, sigma_bl
