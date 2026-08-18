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
