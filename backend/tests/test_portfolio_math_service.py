import numpy as np
import pandas as pd

from app.services.portfolio_math_service import ledoit_wolf_shrinkage, market_implied_risk_aversion


def test_ledoit_wolf_shrinkage_returns_symmetric_positive_semidefinite():
    rng = np.random.default_rng(42)
    returns = rng.normal(0, 0.01, size=(252, 5))
    cov = ledoit_wolf_shrinkage(returns)
    assert cov.shape == (5, 5)
    assert np.allclose(cov, cov.T)
    eigenvalues = np.linalg.eigvalsh(cov)
    assert (eigenvalues >= -1e-10).all()


def test_ledoit_wolf_shrinkage_shrinks_toward_diagonal_vs_sample_cov():
    rng = np.random.default_rng(1)
    returns = rng.normal(0, 0.01, size=(60, 8))  # small sample -> shrinkage should matter
    sample_cov = np.cov(returns, rowvar=False)
    shrunk = ledoit_wolf_shrinkage(returns) / 252  # de-annualize for comparison
    off_diag_sample = np.abs(sample_cov[~np.eye(8, dtype=bool)]).mean()
    off_diag_shrunk = np.abs(shrunk[~np.eye(8, dtype=bool)]).mean()
    assert off_diag_shrunk < off_diag_sample


def test_market_implied_risk_aversion_matches_closed_form():
    dates = pd.date_range("2023-01-01", periods=252, freq="B")
    rng = np.random.default_rng(7)
    daily_returns = rng.normal(0.0004, 0.01, size=252)
    prices = pd.Series(100 * (1 + daily_returns).cumprod(), index=dates)

    delta = market_implied_risk_aversion(prices, risk_free_rate_pct=4.0)

    daily = prices.pct_change().dropna()
    annual_return = daily.mean() * 252
    annual_var = daily.var() * 252
    expected_delta = (annual_return - 0.04) / annual_var
    assert abs(delta - expected_delta) < 1e-6
