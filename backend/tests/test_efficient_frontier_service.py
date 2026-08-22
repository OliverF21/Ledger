# backend/tests/test_efficient_frontier_service.py
import numpy as np
import pytest

from app.services.efficient_frontier_service import (
    TRADING_DAYS_PER_YEAR,
    sample_random_portfolios,
    sweep_efficient_frontier,
)


def test_frontier_points_are_annualized_to_match_portfolio_stats():
    # Regression test for the scale-mismatch bug flagged in PR #23: this
    # module used to report raw daily-scale mu/cov values (just x100 for a
    # "percentage" that wasn't actually one), while the objective markers
    # plotted alongside this curve (EfficientFrontierChart.tsx, fed by
    # portfolio_stats() in price_matrix_service.py) are annualized --
    # return x365, volatility x sqrt(365). That put the two objective
    # markers ~365x/~19x off the curve's scale on the chart.
    #
    # Two uncorrelated assets with different means/variances, chosen so
    # both ends of the swept range are hand-computable exactly:
    #   - min-vol end: the classical two-asset min-variance weights
    #     w_A = varB/(varA+varB) = 0.8, w_B = varA/(varA+varB) = 0.2
    #     (a standard result, independent of mu), giving
    #     var = 0.8^2*0.01 + 0.2^2*0.04 = 0.008 -> vol = sqrt(0.008).
    #   - max-vol/max-return end: portfolio variance w^2*varA + (1-w)^2*varB
    #     is convex in w with its minimum at w=0.8, so its maximum over
    #     w in [0, 1] is at a boundary -- var(0)=varB=0.04 > var(1)=varA=0.01
    #     -- making w=(0, 1) (pure asset B, the higher-mean asset) the
    #     unique point at the top of the swept range, forced by BOTH the
    #     min/max-volatility bracket step and the return-maximizing solve.
    mu = np.array([0.20, 0.35])
    cov = np.array([[0.10**2, 0.0], [0.0, 0.20**2]])
    bounds = [(0.0, 1.0), (0.0, 1.0)]

    points = sweep_efficient_frontier(mu, cov, bounds, sector_constraints=None, n_points=3)

    assert len(points) == 3
    expected_min_vol_pct = np.sqrt(0.008) * np.sqrt(TRADING_DAYS_PER_YEAR) * 100
    expected_min_vol_return_pct = (0.8 * 0.20 + 0.2 * 0.35) * TRADING_DAYS_PER_YEAR * 100
    assert points[0]["volatility_pct"] == pytest.approx(expected_min_vol_pct, rel=1e-3)
    assert points[0]["return_pct"] == pytest.approx(expected_min_vol_return_pct, rel=1e-3)

    expected_max_vol_pct = 0.20 * np.sqrt(TRADING_DAYS_PER_YEAR) * 100
    expected_max_vol_return_pct = 0.35 * TRADING_DAYS_PER_YEAR * 100
    assert points[-1]["volatility_pct"] == pytest.approx(expected_max_vol_pct, rel=1e-3)
    assert points[-1]["return_pct"] == pytest.approx(expected_max_vol_return_pct, rel=1e-3)


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
    # NOTE: a 2-asset sum-to-1 problem can NEVER exercise the drop branch,
    # no matter how narrow the bounds -- w2 = 1 - w1 is forced, so any w1 in
    # a symmetric [(lo, hi), (lo, hi)] box keeps w2 in its identical bound
    # too. Narrow bounds only shrink the achievable-volatility range, they
    # never fragment it, so the swept range stays fully continuous and
    # SLSQP converges everywhere (confirmed empirically: the previous
    # version of this test, with mu=[0.50, 0.02],
    # cov=[[0.25, 0.0], [0.0, 0.001]], bounds=[(0.45, 0.55), (0.45, 0.55)],
    # converged on all 10/10 points -- the `continue` drop branch in
    # sweep_efficient_frontier was never actually hit).
    #
    # This scenario instead uses 4 assets: two of them (indices 0, 1) are
    # highly (~0.97) correlated with large, differing variances -- which
    # drives up the covariance matrix's condition number (~134 here, vs.
    # a well-conditioned matrix's ~1) -- combined with tight,
    # individually-tailored per-asset bounds. Both ingredients are
    # individually realistic (correlated assets; per-ticker min/max
    # position bounds); combined, they make the per-target-volatility SLSQP
    # solve genuinely numerically hard. Verified empirically (see Task 12
    # fix-round report) that this reliably drops 6 of the 10 swept target
    # volatilities -- SLSQP fails each with "Positive directional
    # derivative for linesearch" (a real solver non-convergence, not a
    # fabricated one), while the other 4 (the lower-volatility end of the
    # swept range) converge normally. Re-run twice during verification to
    # confirm determinism (SLSQP has no randomness, so this is stable
    # across runs given fixed inputs).
    mu = np.array([0.29, 0.00, 0.34, 0.30])
    cov = np.array([
        [0.50, 0.48, 0.006, -0.01],
        [0.48, 0.49, 0.006, -0.01],
        [0.006, 0.006, 0.85, 0.0015],
        [-0.01, -0.01, 0.0015, 0.0075],
    ])
    bounds = [(0.20, 0.38), (0.13, 0.27), (0.16, 0.54), (0.12, 0.15)]

    points = sweep_efficient_frontier(mu, cov, bounds, sector_constraints=None, n_points=10)

    # Strict "<" (not "<="): whatever comes back must be a PROVEN strict
    # subset of the 10 requested points, not a full 10-point curve padded
    # with equal-weight fallbacks -- and if this scenario ever stops
    # exercising the drop branch (e.g. a future scipy upgrade makes SLSQP
    # converge everywhere), this assertion fails loudly instead of quietly
    # passing on a vacuous scenario again.
    assert len(points) < 10
    assert len(points) > 0  # and not *everything* should fail either
    for p in points:
        assert p["volatility_pct"] > 0
    vols = [p["volatility_pct"] for p in points]
    assert vols == sorted(vols)  # surviving points still swept in increasing order


def test_random_portfolios_are_annualized_and_bounded_by_extremes():
    # Same annualization convention as sweep_efficient_frontier -- see
    # test_frontier_points_are_annualized_to_match_portfolio_stats above for
    # why this matters (this cloud renders on the same chart/axes as that
    # curve and the objective markers, so all three must agree on scale).
    mu = np.array([0.20, 0.35])
    cov = np.array([[0.10**2, 0.0], [0.0, 0.20**2]])

    points = sample_random_portfolios(mu, cov, risk_free_rate_pct=2.0, n_samples=400)

    assert len(points) == 400  # 200 + 200, from the two Dirichlet blends
    # Every sample is a convex combination (Dirichlet sums to 1, no
    # shorting) of two assets whose individual annualized vols/returns
    # bound the whole simplex -- so no sample point should fall outside the
    # box spanned by the two pure-asset corners, regardless of which random
    # draw came out.
    max_possible_vol_pct = 0.20 * np.sqrt(TRADING_DAYS_PER_YEAR) * 100 * 1.001  # tiny slack for float rounding
    min_possible_return_pct = 0.20 * TRADING_DAYS_PER_YEAR * 100 * 0.999
    max_possible_return_pct = 0.35 * TRADING_DAYS_PER_YEAR * 100 * 1.001
    for p in points:
        assert 0 <= p["volatility_pct"] <= max_possible_vol_pct
        assert min_possible_return_pct <= p["return_pct"] <= max_possible_return_pct
        assert isinstance(p["sharpe"], float)
