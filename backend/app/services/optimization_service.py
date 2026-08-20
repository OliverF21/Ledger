# backend/app/services/optimization_service.py
"""
Suggested portfolio allocation across currently-held tickers, using a
mean-variance optimizer (scipy SLSQP rather than PyPortfolioOpt/cvxpy — see
plan doc for why: cvxpy's solver backends are a known headache to bundle into
the PyInstaller desktop build, and SLSQP is more than sufficient for this
book's size, ~5-30 holdings).

Basic mode (User.optimization_advanced_enabled == False, the default): a
single max-Sharpe solve over historical-mean returns and a Ledoit-Wolf-
shrunk covariance, bounded by a user-configurable position cap. Advanced
mode blends Black-Litterman returns (market-implied prior + ETF trailing-
mean views via Idzorek) with sector/ticker constraints, a concentration
(HHI-style) penalty, two solves -- max-Sharpe and max-quadratic-utility
(Tasks 10-11) -- and an efficient-frontier sweep across target
volatilities (Task 12).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sqlalchemy.orm import Session

from app.models import TickerClassification, User
from app.risk_free_rate import get_cached_risk_free_rate
from app.services.efficient_frontier_service import sweep_efficient_frontier
from app.services.investment_service import _investment_accounts
from app.services.portfolio_math_service import (
    TRADING_DAYS_PER_YEAR as LEDOIT_WOLF_ANNUALIZATION_DAYS,
    black_litterman_posterior,
    concentration_gammas,
    idzorek_omega,
    ledoit_wolf_shrinkage,
    market_implied_prior,
    market_implied_risk_aversion,
)
from app.services.price_matrix_service import (
    current_weights,
    held_tickers,
    portfolio_stats,
    price_matrix,
    priceable_tickers,
)
from app.services.sector_constraint_service import (
    build_sector_exposure_matrix,
    build_ticker_bounds,
    clip_sector_bounds,
    relax_position_cap_if_needed,
)

TRADING_DAYS_PER_YEAR = 365
MIN_LOOKBACK_ROWS = 30
# Documented default for User.optimization_position_cap_pct (models.py). Used
# only as a fallback when the column reads NULL -- e.g. a pre-existing DB row
# from before this migration; see models.py:55-58. Its ORM `default=` only
# applies to newly-inserted rows, not ALTER TABLE-added columns on existing
# ones, so callers must coalesce NULL explicitly rather than trust the ORM
# default has taken effect.
DEFAULT_POSITION_CAP_PCT = 10.0
# Documented default for User.optimization_concentration_strength (models.py).
# Same NULL-on-pre-existing-rows rationale/mechanism as DEFAULT_POSITION_CAP_PCT
# above -- see models.py:55-58.
DEFAULT_CONCENTRATION_STRENGTH = 0.5


@dataclass(frozen=True)
class TickerWeight:
    ticker: str
    current_weight_pct: float
    suggested_weight_pct: float


@dataclass(frozen=True)
class ObjectiveResult:
    """One optimizer solve's output. Basic mode always produces exactly one
    ObjectiveResult (name="max_sharpe"); advanced mode (Task 10+) adds a
    second ("max_quadratic_utility"). `tickers` reuses TickerWeight (current
    + suggested paired together) rather than a leaner ticker/weight-only
    shape: each objective is meant to be a self-contained "current vs. this
    objective's suggestion" view a caller/UI can render on its own (e.g. one
    card per objective) without cross-referencing OptimizationData.tickers
    for the current side. The small duplication of current_weight_pct across
    objectives (identical every time, since "current" doesn't vary by
    objective) is cheap and avoids introducing a second near-identical
    per-ticker dataclass for marginal benefit.

    expected_return_pct/volatility_pct are plain floats, not float | None:
    an ObjectiveResult only ever exists after a real solve has produced
    portfolio_stats output (never for the insufficient-data path, which
    short-circuits to an empty `objectives` list instead) -- so "no value"
    is represented by the objective's absence, not by None fields here.
    sharpe stays Optional because portfolio_stats itself can return None
    for a zero-volatility portfolio regardless of data sufficiency."""
    name: str
    tickers: list[TickerWeight]
    expected_return_pct: float
    volatility_pct: float
    sharpe: float | None


@dataclass(frozen=True)
class OptimizationData:
    tickers: list[TickerWeight]
    current_expected_return_pct: float | None
    current_volatility_pct: float | None
    current_sharpe: float | None
    suggested_expected_return_pct: float | None
    suggested_volatility_pct: float | None
    suggested_sharpe: float | None
    data_points: int
    insufficient_data: bool
    advanced_enabled: bool
    position_cap_pct: float
    cap_relaxed: dict | None
    objectives: list[ObjectiveResult]
    frontier_points: list[dict] | None
    sector_breakdown: list[dict] | None
    clip_log: list[dict]


def _empty_result(data_points: int = 0) -> OptimizationData:
    return OptimizationData(
        tickers=[], current_expected_return_pct=None, current_volatility_pct=None, current_sharpe=None,
        suggested_expected_return_pct=None, suggested_volatility_pct=None, suggested_sharpe=None,
        data_points=data_points, insufficient_data=True,
        advanced_enabled=False, position_cap_pct=0.0, cap_relaxed=None,
        objectives=[], frontier_points=None, sector_breakdown=None, clip_log=[],
    )


def neg_utility_bl(
    weights: np.ndarray, mu_bl: np.ndarray, sigma_bl: np.ndarray, delta: float, gamma_utility: float
) -> float:
    """Max Quadratic Utility, negated for scipy's minimizer:
    -(w'mu - 0.5*delta*w'Sigma*w) + gamma*sum(w^2), the standard mean-
    variance utility an investor with risk-aversion `delta` would maximize.
    A second, differently-shaped view of the same mu_bl/sigma_bl BL-posterior
    inputs the max-Sharpe solve uses, not a variant of Sharpe itself. Same
    concentration-penalty idiom as neg_sharpe_bl, independently scaled via
    gamma_utility since this objective's natural magnitude differs from
    Sharpe's.

    `mu_bl`/`sigma_bl` are DAILY-scale (build_optimization_suggestion divides
    `cov` back to daily terms before any BL call, and portfolio_stats /
    neg_sharpe_bl both annualize them themselves). Both terms are annualized
    here to match that convention. That is load-bearing, not cosmetic:
    GAMMA_UTILITY_SCALE = 0.3 is calibrated against an ANNUAL-scale utility
    (portfolio_math_service.py's own comment pins the assumed range at
    "utility ~O(0.01-0.5)"). Left unannualized, utility ran ~1/365th of that,
    so the gamma_utility concentration penalty dominated the objective by
    ~2 orders of magnitude and collapsed this solve to near-equal-weighting
    at every concentration_strength -- measured at the 0.5 default: 0.43pp
    max deviation from equal weight, vs. the max-Sharpe solve's 7.80pp on
    identical inputs. That defeated the point of running two differentiated
    objectives at all.

    Mean returns annualize LINEARLY (x TRADING_DAYS_PER_YEAR); so does
    variance, since the variance of an i.i.d. sum scales with time -- it is
    x TRADING_DAYS_PER_YEAR, NOT x sqrt(...). The sqrt in neg_sharpe_bl is
    there because Sharpe's denominator is a standard deviation, not a
    variance; there is no sqrt here because quadratic utility penalizes
    variance directly.

    `delta` is deliberately NOT rescaled: market_implied_risk_aversion
    computes it as (annual excess return) / (annual variance), so it is
    already an annual-terms coefficient and multiplying an annualized
    variance by it is dimensionally correct as-is.

    Module-level (unlike neg_sharpe_bl, which stays a closure inside
    build_optimization_suggestion) specifically so this annualization
    convention can be pinned by a direct hand-computed unit test -- see
    tests/test_optimization_service.py::test_neg_utility_bl_annualizes_*.
    """
    annual_return = float(weights @ mu_bl) * TRADING_DAYS_PER_YEAR
    annual_variance = float(weights @ sigma_bl @ weights) * TRADING_DAYS_PER_YEAR
    utility = annual_return - 0.5 * delta * annual_variance
    return -utility + gamma_utility * float(np.sum(weights**2))


def _build_ticker_weights_and_objective(
    name: str,
    tickers: list[str],
    current_weights_pct: dict[str, float],
    suggested_weights: np.ndarray,
    suggested_return: float,
    suggested_vol: float,
    suggested_sharpe: float | None,
) -> tuple[list[TickerWeight], ObjectiveResult, float | None]:
    """Shared by both basic mode and advanced mode's Max Sharpe solve: turns
    a solved weight vector into the paired TickerWeight list and its single
    ObjectiveResult. The only inputs that differ between the two current
    call sites are the stats themselves (basic mode's plain mean/cov-derived
    numbers vs. advanced mode's BL-derived mu_bl/sigma_bl-derived numbers)
    and `name` -- both currently pass "max_sharpe", but Tasks 11-12 add a
    second objective ("max_quadratic_utility") to the advanced branch, which
    is why `name` is a parameter rather than hardcoded here.

    Also returns `suggested_sharpe_rounded` separately (not just embedded in
    the returned ObjectiveResult) since both call sites additionally thread
    that same rounded value through to the top-level
    `OptimizationData.suggested_sharpe` field."""
    ticker_weights = [
        TickerWeight(
            ticker=t,
            current_weight_pct=round(current_weights_pct[t], 2),
            suggested_weight_pct=round(float(suggested_weights[i]) * 100, 2),
        )
        for i, t in enumerate(tickers)
    ]
    suggested_sharpe_rounded = round(suggested_sharpe, 2) if suggested_sharpe is not None else None
    objective = ObjectiveResult(
        name=name,
        tickers=ticker_weights,
        expected_return_pct=round(suggested_return, 2),
        volatility_pct=round(suggested_vol, 2),
        sharpe=suggested_sharpe_rounded,
    )
    return ticker_weights, objective, suggested_sharpe_rounded


def build_optimization_suggestion(db: Session, *, lookback_days: int = 365) -> OptimizationData:
    lookback_days = max(90, min(int(lookback_days), 1825))
    end = date.today()
    start = end - timedelta(days=lookback_days)

    accounts = _investment_accounts(db)
    account_ids = [a.id for a in accounts]
    tickers = held_tickers(db, account_ids)
    if len(tickers) < 2:
        return _empty_result()

    tickers = priceable_tickers(db, tickers, start, end)
    if len(tickers) < 2:
        return _empty_result()

    dates, prices = price_matrix(db, tickers, start, end)
    if len(dates) < MIN_LOOKBACK_ROWS:
        return _empty_result(data_points=len(dates))

    returns = prices[1:] / prices[:-1] - 1
    mean_returns = returns.mean(axis=0)
    # ledoit_wolf_shrinkage annualizes internally using a 252-trading-day
    # convention (portfolio_math_service.TRADING_DAYS_PER_YEAR), but
    # portfolio_stats/neg_sharpe below expect a DAILY covariance and do
    # their own annualization using this codebase's established 365-
    # calendar-day convention (TRADING_DAYS_PER_YEAR above -- matches
    # mean_returns' annualization here and in risk_service.py /
    # price_matrix_service.py). Feeding the already-annualized output
    # straight into that unchanged pipeline would double-annualize (vol
    # inflated by sqrt(252), Sharpe deflated by the same factor -- a
    # uniform positive rescale, so it wouldn't change which weights win,
    # but it would corrupt every *reported* volatility/Sharpe number).
    # Divide back to daily terms so the improved (shrunk) covariance
    # estimate composes correctly with the unchanged downstream
    # annualization.
    cov = ledoit_wolf_shrinkage(returns) / LEDOIT_WOLF_ANNUALIZATION_DAYS
    risk_free_rate_pct = get_cached_risk_free_rate(db)

    current_weights_pct = current_weights(db, account_ids, tickers)
    current_weight_fractions = np.array([current_weights_pct[t] / 100 for t in tickers])
    current_return, current_vol, current_sharpe = portfolio_stats(current_weight_fractions, mean_returns, cov, risk_free_rate_pct)

    n = len(tickers)

    user = db.query(User).filter_by(id=1).one()
    # NULL-coalesce: these columns land NULL (not their declared ORM
    # defaults) on any pre-existing DB row that predates the migration
    # adding them -- see models.py:55-58. The documented default for
    # optimization_advanced_enabled is False, so NULL -> False is correct
    # and matches intent (not just "None is falsy" incidentally).
    advanced = False if user.optimization_advanced_enabled is None else bool(user.optimization_advanced_enabled)
    requested_cap_pct = (
        DEFAULT_POSITION_CAP_PCT if user.optimization_position_cap_pct is None else float(user.optimization_position_cap_pct)
    )
    requested_cap = requested_cap_pct / 100

    effective_cap, cap_relax_log = relax_position_cap_if_needed(n, requested_cap)

    if advanced:
        # Concentration penalty + Max Quadratic Utility objective (Task 11)
        # plus the efficient-frontier sweep (Task 12). This branch returns
        # two BL-driven ObjectiveResults (max_sharpe, max_quadratic_utility)
        # with sector_breakdown and frontier_points populated.
        spy_dates, spy_prices = price_matrix(db, ["SPY"], start, end)
        if len(spy_dates) < 2:
            # SPY is a guaranteed benchmark ticker per price_sync_service.py's
            # BENCHMARK_TICKERS -- this should only happen if the initial
            # price sync hasn't run yet. Fail loud with a clear diagnostic
            # rather than an IndexError from indexing an empty price matrix
            # below; routes/portfolio_risk.py's try/except degrades either
            # one to a normal 500 the same way.
            raise ValueError("advanced mode requires SPY benchmark price history")
        spy_series = pd.Series(spy_prices[:, 0])
        delta = market_implied_risk_aversion(spy_series, risk_free_rate_pct)

        classifications = db.query(TickerClassification).filter(TickerClassification.ticker.in_(tickers)).all()
        classification_by_ticker = {c.ticker: c for c in classifications}

        # Market-cap/AUM-weighted "market portfolio" over the same tickers
        # as cov's rows/columns -- the AUM-fallback fix validated in the
        # example script (ETFs report AUM via a different yfinance field
        # than ordinary equities' market cap; TickerClassification already
        # coalesces both into one market_cap_or_aum column upstream, so no
        # separate fallback is needed here beyond treating a missing
        # classification or a NULL value as 0 exposure). If nothing has
        # been classified yet (e.g. sector_sync_service.py hasn't run),
        # fall back to an equally-weighted market rather than dividing by
        # zero -- this only shifts the BL prior's starting point; the
        # sector/ticker constraints below read TickerClassification
        # independently and are unaffected.
        market_caps = np.array([
            float(classification_by_ticker[t].market_cap_or_aum)
            if t in classification_by_ticker and classification_by_ticker[t].market_cap_or_aum is not None
            else 0.0
            for t in tickers
        ])
        total_market_cap = market_caps.sum()
        market_weights = market_caps / total_market_cap if total_market_cap > 0 else np.full(n, 1.0 / n)

        # black_litterman_posterior inverts (tau * cov) directly via
        # np.linalg.inv, which raises LinAlgError: Singular matrix if cov
        # contains ANY zero-variance asset. This is a real, expected input
        # class here, not a hypothetical: ledoit_wolf_shrinkage's own test
        # suite establishes zero-variance tickers (stale/halted/constant-
        # price securities) as first-class supported input, and a PSD
        # covariance matrix with one zero-variance asset is guaranteed to
        # have that asset's entire row/column be exactly zero -- which
        # makes tau*cov singular regardless of every other asset's data
        # quality. idzorek_omega's existing epsilon-floor guard (Task 5)
        # only protects omega's own inversion, not this separate one.
        # Floor the covariance diagonal before any BL call rather than
        # letting one degenerate ticker crash the whole advanced-mode solve
        # for the entire book, or silently dropping it from advanced mode's
        # output only (which basic mode would still show -- a confusing
        # inconsistency for a user toggling the mode). Off-diagonal entries
        # are left untouched: a true zero-variance asset has zero
        # covariance with everything by definition (Cov(X,Y)=0 when
        # Var(X)=0), so only the diagonal needs nudging off of exactly
        # zero. Mirrors the same floor-before-inverting idiom
        # ledoit_wolf_shrinkage (std floor) and idzorek_omega (omega floor)
        # already use elsewhere in this pipeline.
        cov_for_bl = cov.copy()
        np.fill_diagonal(cov_for_bl, np.maximum(np.diag(cov_for_bl), 1e-10))

        pi = market_implied_prior(cov_for_bl, market_weights, delta)

        etf_indices = [
            i for i, t in enumerate(tickers)
            if classification_by_ticker.get(t) is not None and classification_by_ticker[t].asset_class == "etf"
        ]
        if etf_indices:
            P = np.zeros((len(etf_indices), n))
            Q = np.zeros(len(etf_indices))
            for row, i in enumerate(etf_indices):
                P[row, i] = 1.0
                Q[row] = mean_returns[i]
            omega = idzorek_omega([0.3] * len(etf_indices), P, tau=0.05, cov=cov_for_bl)
            mu_bl, sigma_bl = black_litterman_posterior(cov_for_bl, pi, P, Q, omega, tau=0.05)
        else:
            # No ETF held -> no views to blend; Black-Litterman with zero
            # views collapses to the market-implied prior itself.
            mu_bl, sigma_bl = pi, cov_for_bl

        exposure_matrix, sector_names = build_sector_exposure_matrix(db, tickers)
        sector_lower, sector_upper, clip_log = clip_sector_bounds(db, 1, sector_names, exposure_matrix, effective_cap)
        ticker_lower, ticker_upper = build_ticker_bounds(db, 1, tickers, effective_cap)

        # NULL-coalesce, same pattern/rationale as `advanced`/`requested_cap_pct`
        # in the shared preamble above (models.py:55-58): a pre-existing DB
        # row predating this column's migration reads NULL here too, despite
        # the column's declared ORM default (0.5).
        concentration_strength = (
            DEFAULT_CONCENTRATION_STRENGTH if user.optimization_concentration_strength is None
            else float(user.optimization_concentration_strength)
        )
        gamma_sharpe, gamma_utility = concentration_gammas(concentration_strength)

        def neg_sharpe_bl(weights: np.ndarray) -> float:
            ret = np.dot(weights, mu_bl) * TRADING_DAYS_PER_YEAR
            vol = np.sqrt(weights @ sigma_bl @ weights) * np.sqrt(TRADING_DAYS_PER_YEAR)
            if vol == 0:
                return 0.0
            return -(ret - risk_free_rate_pct / 100) / vol + gamma_sharpe * np.sum(weights**2)

        # The quadratic-utility objective itself lives at module level
        # (neg_utility_bl, above) rather than as a closure here -- see its
        # docstring for why. `delta` is the same SPY-derived risk-aversion
        # coefficient computed near the top of this branch, per
        # market_implied_risk_aversion's own docstring: "Used both to build
        # the Black-Litterman prior AND as the quadratic-utility objective's
        # risk-aversion parameter".

        # Per-sector inequality constraints live in their own list (rather
        # than being appended straight into advanced_constraints) because
        # Task 12's frontier sweep (sweep_efficient_frontier, below) also
        # needs them standalone: it prepends its own sum-to-one equality
        # constraint internally, so handing it advanced_constraints
        # (which already has one) would duplicate that equality constraint
        # into every one of the sweep's solves.
        sector_scipy_constraints = []
        for j in range(len(sector_names)):
            col = exposure_matrix[:, j]
            lo = sector_lower[j]
            hi = sector_upper[j]
            # Bind col/lo/hi as default args, not a bare closure over the
            # loop variables -- scipy only calls these `fun`s AFTER this
            # loop finishes building the whole constraints list, so a bare
            # `lambda w: col @ w - lo` would have every constraint
            # reference the SAME (final) col/lo/hi from the last iteration,
            # silently applying only the last sector's bounds to every
            # sector. Default args are evaluated once, at lambda-definition
            # time (i.e. per-iteration here), so each constraint keeps its
            # own sector's values independently.
            sector_scipy_constraints.append({"type": "ineq", "fun": lambda w, col=col, lo=lo: col @ w - lo})
            sector_scipy_constraints.append({"type": "ineq", "fun": lambda w, col=col, hi=hi: hi - col @ w})
        advanced_constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}] + sector_scipy_constraints

        bounds = list(zip(ticker_lower, ticker_upper))
        initial = np.array([1.0 / n] * n)

        result = minimize(neg_sharpe_bl, initial, method="SLSQP", bounds=bounds, constraints=advanced_constraints)
        suggested_weights = result.x if result.success else initial
        suggested_return, suggested_vol, suggested_sharpe = portfolio_stats(suggested_weights, mu_bl, sigma_bl, risk_free_rate_pct)

        ticker_weights, max_sharpe_objective, suggested_sharpe_rounded = _build_ticker_weights_and_objective(
            "max_sharpe", tickers, current_weights_pct, suggested_weights, suggested_return, suggested_vol, suggested_sharpe,
        )

        # Second, independent solve: same bounds/constraints (sector floors/
        # caps, ticker minimums, sum-to-1) as the max-Sharpe solve above, but
        # a different objective function (neg_utility_bl) -- so it's
        # expected to (and, per this task's own verification, empirically
        # does) generally converge to a different weight vector.
        utility_result = minimize(
            neg_utility_bl, initial, args=(mu_bl, sigma_bl, delta, gamma_utility),
            method="SLSQP", bounds=bounds, constraints=advanced_constraints,
        )
        suggested_weights_utility = utility_result.x if utility_result.success else initial
        suggested_return_utility, suggested_vol_utility, suggested_sharpe_utility = portfolio_stats(
            suggested_weights_utility, mu_bl, sigma_bl, risk_free_rate_pct,
        )
        # Reuses _build_ticker_weights_and_objective (Task 10's fix-round
        # helper, added specifically so this task wouldn't need a third
        # near-duplicate ticker-weights/ObjectiveResult construction block).
        # Its ticker-weights/rounded-sharpe return values aren't needed here:
        # the top-level OptimizationData.tickers/suggested_* fields stay
        # tied to the max_sharpe objective (unchanged from Task 10), and
        # this objective's own tickers already live inside
        # max_utility_objective.tickers.
        _, max_utility_objective, _ = _build_ticker_weights_and_objective(
            "max_quadratic_utility", tickers, current_weights_pct, suggested_weights_utility,
            suggested_return_utility, suggested_vol_utility, suggested_sharpe_utility,
        )
        objectives = [max_sharpe_objective, max_utility_objective]

        # Efficient-frontier sweep (Task 12): independent SLSQP solves at a
        # range of target volatilities spanning the achievable min-volatility
        # portfolio through the max-return portfolio's volatility, using the
        # same BL posterior (mu_bl/sigma_bl) and ticker/sector constraints as
        # both solves above. Passes sector_scipy_constraints (the per-sector
        # inequalities only) rather than advanced_constraints -- see the
        # comment where sector_scipy_constraints is built above --
        # sweep_efficient_frontier prepends its own sum-to-one equality
        # constraint internally.
        frontier_points = sweep_efficient_frontier(
            mu_bl, sigma_bl, bounds, sector_scipy_constraints, n_points=20,
        )

        # floor_pct/cap_pct reuse the lower/upper vectors clip_sector_bounds
        # already returned above (rather than re-reading the raw
        # SectorConstraint rows) so the reported figures reflect any
        # auto-clipping that happened -- e.g. a floor request that exceeded
        # what's achievable given the position cap shows the ACHIEVABLE
        # (clipped) floor here, matching what the solver was actually asked
        # to enforce, not the user's original unclipped request.
        sector_breakdown = [
            {
                "sector": s,
                "weight_pct": float(exposure_matrix[:, j] @ suggested_weights * 100),
                "floor_pct": float(sector_lower[j] * 100),
                "cap_pct": float(sector_upper[j] * 100),
            }
            for j, s in enumerate(sector_names)
        ]

        return OptimizationData(
            tickers=ticker_weights,
            current_expected_return_pct=round(current_return, 2),
            current_volatility_pct=round(current_vol, 2),
            current_sharpe=round(current_sharpe, 2) if current_sharpe is not None else None,
            suggested_expected_return_pct=round(suggested_return, 2),
            suggested_volatility_pct=round(suggested_vol, 2),
            suggested_sharpe=suggested_sharpe_rounded,
            data_points=len(dates),
            insufficient_data=False,
            advanced_enabled=True,
            position_cap_pct=round(effective_cap * 100, 2),
            cap_relaxed=cap_relax_log,
            objectives=objectives,
            frontier_points=frontier_points,
            sector_breakdown=sector_breakdown,
            clip_log=clip_log,
        )

    def neg_sharpe(weights: np.ndarray) -> float:
        ret = np.dot(weights, mean_returns) * TRADING_DAYS_PER_YEAR
        vol = np.sqrt(weights @ cov @ weights) * np.sqrt(TRADING_DAYS_PER_YEAR)
        if vol == 0:
            return 0.0
        return -(ret - risk_free_rate_pct / 100) / vol

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0.0, effective_cap)] * n
    initial = np.array([1.0 / n] * n)

    result = minimize(neg_sharpe, initial, method="SLSQP", bounds=bounds, constraints=constraints)
    suggested_weights = result.x if result.success else initial
    suggested_return, suggested_vol, suggested_sharpe = portfolio_stats(suggested_weights, mean_returns, cov, risk_free_rate_pct)

    ticker_weights, max_sharpe_objective, suggested_sharpe_rounded = _build_ticker_weights_and_objective(
        "max_sharpe", tickers, current_weights_pct, suggested_weights, suggested_return, suggested_vol, suggested_sharpe,
    )
    objectives = [max_sharpe_objective]

    return OptimizationData(
        tickers=ticker_weights,
        current_expected_return_pct=round(current_return, 2),
        current_volatility_pct=round(current_vol, 2),
        current_sharpe=round(current_sharpe, 2) if current_sharpe is not None else None,
        suggested_expected_return_pct=round(suggested_return, 2),
        suggested_volatility_pct=round(suggested_vol, 2),
        suggested_sharpe=suggested_sharpe_rounded,
        data_points=len(dates),
        insufficient_data=False,
        advanced_enabled=False,
        position_cap_pct=round(effective_cap * 100, 2),
        cap_relaxed=cap_relax_log,
        objectives=objectives,
        frontier_points=None,
        sector_breakdown=None,
        clip_log=[],
    )
