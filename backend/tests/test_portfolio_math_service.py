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


def test_ledoit_wolf_shrinkage_handles_zero_variance_asset():
    # A constant (zero-variance) asset -- e.g. a stale or halted price feed
    # -- must not NaN-poison the other assets' covariance entries. Before
    # the epsilon floor on std, corr's row/column for the degenerate asset
    # was 0/0 = NaN, which propagated through the pooled avg_corr scalar
    # into every entry of `target`, and from there into the whole result.
    rng = np.random.default_rng(3)
    returns = rng.normal(0, 0.01, size=(100, 4))
    returns[:, 1] = 0.0  # constant price series -> exactly zero variance

    cov = ledoit_wolf_shrinkage(returns)

    assert cov.shape == (4, 4)
    assert np.isfinite(cov).all()
    assert np.allclose(cov, cov.T)
    eigenvalues = np.linalg.eigvalsh(cov)
    assert (eigenvalues >= -1e-10).all()
    # The degenerate asset has no real covariation with anything (including
    # itself): its entire row/column should be exactly zero, not NaN, and
    # the other three assets' mutual entries must be unaffected/finite.
    assert np.allclose(cov[1, :], 0.0)
    assert np.allclose(cov[:, 1], 0.0)
    other = np.ix_([0, 2, 3], [0, 2, 3])
    assert np.isfinite(cov[other]).all()


def test_ledoit_wolf_shrinkage_matches_independently_computed_intensity():
    # Regression-pins the shrinkage-intensity (kappa/phi/gamma) calculation
    # against a value computed by an independent re-derivation of the
    # formula below -- NOT by calling ledoit_wolf_shrinkage -- so this is a
    # genuine check, not a tautology. Small fixed (non-random) numbers are
    # used so the key intermediate values can also be verified by hand,
    # rather than trusted blindly:
    #
    #   returns: A=[2,4,6,8], B=[1,2,4,5], C=[5,4,2,1] (4 periods, 3 assets)
    #   demeaned: x_A=[-3,-1,1,3], x_B=[-2,-1,1,2], x_C=[2,1,-1,-2]=-x_B
    #   sample_cov = [[5, 3.5, -3.5], [3.5, 2.5, -2.5], [-3.5, -2.5, 2.5]]
    #   var = [5, 2.5, 2.5] (exact in binary: 20/4, 10/4, 10/4)
    #   corr_AB = 3.5/sqrt(12.5), corr_AC = -3.5/sqrt(12.5) (= -corr_AB,
    #     since Cov_AC = -Cov_AB and std_B == std_C exactly), corr_BC = -1
    #     (B, C are exact negatives of each other)
    #   avg_corr = (2*(corr_AB + corr_AC + corr_BC)) / (3*2)
    #            = (2*(0 - 1)) / 6 = -1/3
    #   phi = 50.0 (hand-summable: all inputs are small integers/exact
    #     dyadic fractions, so every intermediate is exact in float64)
    #
    # This pins the current, reviewer-approved formula's numeric behavior
    # so a future code regression (e.g. a wrong axis, dropped annualization
    # factor, or broken clamp) would be caught -- unlike the two tests
    # above, which are satisfied by construction (PSD/symmetry) or by a
    # loose directional inequality on pure noise.
    returns = np.array([
        [2.0, 1.0, 5.0],
        [4.0, 2.0, 4.0],
        [6.0, 4.0, 2.0],
        [8.0, 5.0, 1.0],
    ])

    t, n = returns.shape
    x = returns - returns.mean(axis=0)
    sample_cov = (x.T @ x) / t

    var = np.diag(sample_cov)
    std = np.sqrt(var)
    corr = sample_cov / np.outer(std, std)
    avg_corr = (corr.sum() - n) / (n * (n - 1))
    target = avg_corr * np.outer(std, std)
    np.fill_diagonal(target, var)

    y = x ** 2
    phi = ((y.T @ y) / t - sample_cov ** 2).sum()
    gamma = ((target - sample_cov) ** 2).sum()
    kappa = phi / gamma
    shrinkage = max(0.0, min(1.0, kappa / t))
    expected = (shrinkage * target + (1 - shrinkage) * sample_cov) * 252

    # Hand-verified checkpoints (see derivation above) so the independent
    # re-derivation itself isn't just trusted blindly.
    assert abs(avg_corr - (-1 / 3)) < 1e-9
    assert abs(phi - 50.0) < 1e-9

    actual = ledoit_wolf_shrinkage(returns)
    assert np.allclose(actual, expected, atol=1e-9)


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
