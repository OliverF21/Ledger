# backend/app/services/optimization_service.py
"""
Suggested portfolio allocation across currently-held tickers, using a
mean-variance optimizer (scipy SLSQP rather than PyPortfolioOpt/cvxpy — see
plan doc for why: cvxpy's solver backends are a known headache to bundle into
the PyInstaller desktop build, and SLSQP is more than sufficient for this
book's size, ~5-30 holdings).

There is exactly one optimizer engine: Black-Litterman return blending
(market-implied prior + ETF trailing-mean views via Idzorek) with
sector/ticker constraints, a concentration (HHI-style) penalty, two
solves -- max-Sharpe and max-quadratic-utility -- and an efficient-
frontier sweep across target volatilities.

User.optimization_advanced_enabled (default False) does not select a
different, weaker engine -- it gates whether this module runs at all.
Off means "don't compute or show any optimizer output"; simple portfolio
metrics (Sharpe, VaR, beta, ...) live in risk_service.py and are
unaffected either way. build_optimization_suggestion short-circuits to
_disabled_result() before touching prices/holdings when the toggle is
off, so turning it off is also a real compute saving, not just a UI
hide.
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
from app.services.efficient_frontier_service import sample_random_portfolios, sweep_efficient_frontier
from app.services.investment_service import _investment_accounts
from app.services.portfolio_math_service import (
    TRADING_DAYS_PER_YEAR,
    black_litterman_posterior,
    concentration_gammas,
    idzorek_omega,
    ledoit_wolf_shrinkage,
    market_implied_prior,
    market_implied_risk_aversion,
)
from app.services.price_matrix_service import (
    current_dollar_values,
    held_tickers,
    portfolio_stats,
    price_matrix,
    price_returns,
    priceable_tickers,
)
from app.services.sector_constraint_service import (
    build_sector_exposure_matrix,
    build_ticker_bounds,
    clip_sector_bounds,
    relax_position_cap_if_needed,
)

# Single source of truth, imported above from portfolio_math_service (252
# trading days -- MarketPrice rows exist only on actual trading days for
# equities/ETFs, confirmed via price_provider.py's yf.download() call, which
# returns no weekend/holiday rows). Previously this module, price_matrix_
# service.py, and efficient_frontier_service.py each declared their OWN
# local `TRADING_DAYS_PER_YEAR = 365`, copied from risk_service.py's
# genuinely-different, correctly-365 convention (a daily BalanceSnapshot
# series, observed every calendar day) without checking whether the
# assumption held for this MarketPrice-derived series -- it didn't, and the
# three duplicated constants let this module silently drift from
# portfolio_math_service.py's already-correct 252 (used internally by
# ledoit_wolf_shrinkage/market_implied_risk_aversion below), producing
# Sharpe ratios inflated by a mismatched final annualization step. Divide-
# by/multiply-by the SAME constant everywhere in this pipeline rather than
# re-declaring it, so this can't happen again.
MIN_LOOKBACK_ROWS = 30
# 3 years, matching the reference prototype (framework_portfolio_optimization.py's
# LOOKBACK_YEARS = 3) rather than the 1-year window this shipped with
# originally. A 1-year sample of ~252 trading-day returns is noisy enough on
# its own to swing mean-return/covariance estimates (and therefore the BL
# posterior and every downstream Sharpe/return figure) run to run; a longer
# window is standard practice for exactly this reason and was flagged as
# part of why results felt implausible compared to the pypfopt-based mockup.
DEFAULT_LOOKBACK_DAYS = 1095
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

# Fallback risk-aversion coefficient, substituted when the market-implied
# delta computed from the SPY benchmark comes out non-positive or non-finite
# (see _guarded_risk_aversion). 2.5 is the conventional "typical investor"
# value in the Black-Litterman literature and sits mid-range of what a
# healthy trailing window actually produces here (empirically ~2-4 for SPY
# on a normal window).
FALLBACK_RISK_AVERSION = 2.5
# Below this, delta is treated as unusable rather than merely small. Any
# delta <= 0 is outright sign-broken (see _guarded_risk_aversion); the small
# positive margin additionally catches the near-zero case, where delta is
# technically the right sign but so small that the quadratic-utility
# objective degenerates to pure return-maximization and the market-implied
# prior pi = delta*Sigma*w_mkt collapses to ~0. For reference, delta would
# have to fall below ~0.2% annual excess return on a 15%-vol benchmark to
# land in this band at all.
MIN_USABLE_RISK_AVERSION = 0.1


def _solved_weights(result, initial: np.ndarray, objective_name: str, clip_log: list[dict]) -> np.ndarray:
    """Unwrap a scipy solve, falling back to `initial` (equal weights) when
    it failed to converge -- and RECORDING that fallback in clip_log.

    The fallback itself is deliberate and predates this helper; what's new is
    that it is no longer silent. A non-convergent solve previously returned
    the equal-weight starting guess with nothing anywhere in the response to
    distinguish it from a real optimization result, so the UI rendered a
    plausible-looking "recommendation" that was in fact just 1/n. That's the
    failure mode that made every other bug in this pipeline invisible: an
    inverted sector floor/cap, or a wild Black-Litterman posterior, both
    surface here as `success=False` and used to vanish without trace.

    efficient_frontier_service.py already takes the stricter line for its own
    sweep -- it drops non-convergent points entirely rather than substituting
    one, precisely so a fabricated point can't imply an unachievable
    risk/return combination is reachable. Dropping isn't available here (the
    endpoint has to return SOME allocation), so the equivalent honesty is to
    label the substitution.
    """
    if result.success:
        return result.x
    clip_log.append({
        "reason": (
            f"the {objective_name} solve did not converge "
            f"({getattr(result, 'message', 'no solver message')}); "
            f"showing an equal-weight portfolio as a fallback -- these are NOT "
            f"optimized weights"
        ),
    })
    return initial


def _guarded_risk_aversion(delta: float) -> tuple[float, dict | None]:
    """Clamp a market-implied risk-aversion coefficient to a usable value,
    returning (delta, clip_log_entry_or_None).

    market_implied_risk_aversion computes delta = (annualized benchmark
    excess return) / (annualized benchmark variance). The numerator goes
    NEGATIVE whenever the benchmark's trailing-window return sits below the
    risk-free rate -- which is not exotic: it happens in any bear-market or
    correction-spanning lookback (2022, 2018, 2008, any COVID window). A
    declining synthetic SPY series measured -13.03 against this codebase's
    own fixtures.

    A negative delta is not merely inaccurate, it inverts the meaning of two
    downstream formulas:
      * neg_utility_bl's `- 0.5 * delta * variance` term becomes a POSITIVE
        coefficient on variance, so the objective REWARDS risk instead of
        penalizing it -- it stops being risk-averse and starts seeking the
        most volatile achievable portfolio. Measured on identical inputs,
        the two objectives diverged to +28.66% vs -31.29% expected return.
      * market_implied_prior's pi = delta*Sigma*w_mkt flips sign, so the
        Black-Litterman prior asserts every asset has negative equilibrium
        expected return.

    Substituting a sane constant is the right call over failing the request:
    delta is a *prior* about investor risk preference, not a measurement of
    the user's portfolio. A trailing window that happens to span a drawdown
    says nothing about how risk-averse the user is, so falling back to the
    conventional value is closer to the truth than propagating a sign-broken
    one -- and far better than a 500 on the Investments page. The
    substitution is surfaced in clip_log so it is visible rather than
    silent, matching how every other auto-adjustment in this pipeline
    behaves.
    """
    if np.isfinite(delta) and delta >= MIN_USABLE_RISK_AVERSION:
        return delta, None
    # `reason` alone: ClipLogEntry's fields are all Optional precisely so
    # different producers can fill different subsets (clip_sector_bounds
    # sends sector/requested_floor/clipped_to; relax_position_cap_if_needed
    # sends requested_cap/relaxed_to/reason). Nothing here is a clipped
    # bound, so only the human-readable reason applies.
    return FALLBACK_RISK_AVERSION, {
        "reason": (
            f"market-implied risk aversion computed as {delta:.4g} from the SPY benchmark "
            f"(non-positive or unusable -- the benchmark's trailing return was at or below "
            f"the risk-free rate); substituted the typical value {FALLBACK_RISK_AVERSION} "
            f"for the Black-Litterman prior and the quadratic-utility objective"
        ),
    }


@dataclass(frozen=True)
class TickerWeight:
    ticker: str
    current_weight_pct: float
    suggested_weight_pct: float
    current_dollar: float
    suggested_dollar: float


@dataclass(frozen=True)
class ObjectiveResult:
    """One optimizer solve's output. Each run produces two: max_sharpe and
    max_quadratic_utility. `tickers` reuses TickerWeight (current
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
    random_portfolios: list[dict] | None
    sector_breakdown: list[dict] | None
    clip_log: list[dict]


def _empty_result(data_points: int = 0) -> OptimizationData:
    """Advanced mode is on, but there isn't enough priceable holding data to
    run the solve (fewer than two tickers, or too few overlapping price
    rows)."""
    return OptimizationData(
        tickers=[], current_expected_return_pct=None, current_volatility_pct=None, current_sharpe=None,
        suggested_expected_return_pct=None, suggested_volatility_pct=None, suggested_sharpe=None,
        data_points=data_points, insufficient_data=True,
        advanced_enabled=True, position_cap_pct=0.0, cap_relaxed=None,
        objectives=[], frontier_points=None, random_portfolios=None, sector_breakdown=None, clip_log=[],
    )


def _disabled_result() -> OptimizationData:
    """User.optimization_advanced_enabled is off. Distinct from
    _empty_result(): insufficient_data communicates "the engine ran and
    couldn't", this communicates "the engine didn't run at all" -- the
    caller (routes/portfolio_risk.py, Investments.tsx) uses advanced_enabled
    to decide whether to show the optimizer section, not insufficient_data,
    so this must not be mistaken for a data problem."""
    return OptimizationData(
        tickers=[], current_expected_return_pct=None, current_volatility_pct=None, current_sharpe=None,
        suggested_expected_return_pct=None, suggested_volatility_pct=None, suggested_sharpe=None,
        data_points=0, insufficient_data=False,
        advanced_enabled=False, position_cap_pct=0.0, cap_relaxed=None,
        objectives=[], frontier_points=None, random_portfolios=None, sector_breakdown=None, clip_log=[],
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
    "utility ~O(0.01-0.5)"). Left unannualized, utility ran ~1/252nd of that,
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
    current_dollar_by_ticker: dict[str, float],
    total_value: float,
    suggested_weights: np.ndarray,
    suggested_return: float,
    suggested_vol: float,
    suggested_sharpe: float | None,
) -> tuple[list[TickerWeight], ObjectiveResult, float | None]:
    """Shared by both the max-Sharpe and max-quadratic-utility solves: turns
    a solved weight vector into the paired TickerWeight list and its single
    ObjectiveResult. `name` is a parameter (not hardcoded) since the two
    call sites pass "max_sharpe" and "max_quadratic_utility" respectively.

    suggested_dollar re-applies `total_value` (today's total across held
    tickers) to the suggested weight rather than any hypothetical future
    value -- it answers "what would this weight be worth if I rebalanced
    today", not a forecast.

    Also returns `suggested_sharpe_rounded` separately (not just embedded in
    the returned ObjectiveResult) since both call sites additionally thread
    that same rounded value through to the top-level
    `OptimizationData.suggested_sharpe` field."""
    ticker_weights = [
        TickerWeight(
            ticker=t,
            current_weight_pct=round(current_weights_pct[t], 2),
            suggested_weight_pct=round(float(suggested_weights[i]) * 100, 2),
            current_dollar=round(current_dollar_by_ticker[t], 2),
            suggested_dollar=round(float(suggested_weights[i]) * total_value, 2),
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


def build_optimization_suggestion(db: Session, *, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> OptimizationData:
    user = db.query(User).filter_by(id=1).one()
    # NULL-coalesce: this column lands NULL (not its declared ORM default of
    # False) on any pre-existing DB row that predates the migration adding
    # it -- see models.py:55-58.
    advanced = False if user.optimization_advanced_enabled is None else bool(user.optimization_advanced_enabled)
    if not advanced:
        return _disabled_result()

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

    # price_matrix returns the UNION of every ticker's available dates (see
    # its docstring) -- a NaN cell means that ticker had no price on that
    # date, typically because the date is before the ticker's IPO/listing.
    # A ticker can still have too little of its OWN history to estimate
    # anything useful even though other, longer-lived tickers cleared the
    # len(dates) check above (e.g. a ticker synced only a handful of
    # trading days ago) -- drop those here rather than feeding a near-empty
    # column into ledoit_wolf_shrinkage's pairwise estimation. Same "drop
    # the unusable one, don't fail the whole book" philosophy
    # priceable_tickers already applies to zero-row tickers above.
    observed_counts = (~np.isnan(prices)).sum(axis=0)
    sparse_history_log = [
        {
            "reason": (
                f"{tickers[i]} dropped from the optimizer: only {int(observed_counts[i])} priced days in "
                f"the lookback window (minimum {MIN_LOOKBACK_ROWS})"
            ),
        }
        for i in range(len(tickers)) if observed_counts[i] < MIN_LOOKBACK_ROWS
    ]
    enough_history = observed_counts >= MIN_LOOKBACK_ROWS
    tickers = [t for t, ok in zip(tickers, enough_history) if ok]
    prices = prices[:, enough_history]
    if len(tickers) < 2:
        return _empty_result(data_points=len(dates))

    returns = price_returns(prices)
    mean_returns = np.nanmean(returns, axis=0)
    # ledoit_wolf_shrinkage annualizes internally (x TRADING_DAYS_PER_YEAR),
    # but portfolio_stats/neg_sharpe_bl/neg_utility_bl below expect a DAILY
    # covariance and do their own annualization using the SAME constant --
    # divide back to daily terms here so the improved (shrunk) covariance
    # estimate composes correctly with that unchanged downstream
    # annualization instead of double-annualizing.
    cov = ledoit_wolf_shrinkage(returns) / TRADING_DAYS_PER_YEAR
    risk_free_rate_pct = get_cached_risk_free_rate(db)

    current_dollar_by_ticker = current_dollar_values(db, account_ids, tickers)
    total_value = sum(current_dollar_by_ticker.values())
    current_weights_pct = {
        t: (current_dollar_by_ticker[t] / total_value * 100 if total_value > 0 else 0.0)
        for t in tickers
    }
    current_weight_fractions = np.array([current_weights_pct[t] / 100 for t in tickers])
    n = len(tickers)

    requested_cap_pct = (
        DEFAULT_POSITION_CAP_PCT if user.optimization_position_cap_pct is None else float(user.optimization_position_cap_pct)
    )
    requested_cap = requested_cap_pct / 100

    effective_cap, cap_relax_log = relax_position_cap_if_needed(n, requested_cap)

    # Returns two BL-driven ObjectiveResults (max_sharpe, max_quadratic_utility)
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
    delta, delta_substitution_log = _guarded_risk_aversion(
        market_implied_risk_aversion(spy_series, risk_free_rate_pct)
    )

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
    # letting one degenerate ticker crash the whole solve for the
    # entire book. Off-diagonal entries are left untouched: a true
    # zero-variance asset has zero covariance with everything by
    # definition (Cov(X,Y)=0 when Var(X)=0), so only the diagonal
    # needs nudging off of exactly zero. Mirrors the same
    # floor-before-inverting idiom ledoit_wolf_shrinkage (std floor)
    # and idzorek_omega (omega floor) already use elsewhere in this
    # pipeline.
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

    # Score the current book on the SAME mu/cov the solver uses (BL posterior),
    # not historical arithmetic means. Otherwise "current expected return" and
    # "suggested expected return" are different estimators and the Sharpe
    # comparison on the Investments tab is apples-to-oranges.
    current_return, current_vol, current_sharpe = portfolio_stats(
        current_weight_fractions, mu_bl, sigma_bl, risk_free_rate_pct
    )

    exposure_matrix, sector_names = build_sector_exposure_matrix(db, tickers)
    sector_lower, sector_upper, clip_log = clip_sector_bounds(db, 1, sector_names, exposure_matrix, effective_cap)
    ticker_lower, ticker_upper = build_ticker_bounds(db, 1, tickers, effective_cap)

    # clip_log is the pipeline's single "we auto-adjusted something you
    # asked for" channel, and it's first created above -- so the delta
    # substitution AND any sparse-history ticker drops, both decided back
    # at the top of this branch (where no clip_log existed yet to append
    # to), are folded in here. Prepended rather than appended: they
    # describe inputs to the whole solve, not one constraint's clipping,
    # so they read first in the UI banner.
    prefix_log = sparse_history_log + ([delta_substitution_log] if delta_substitution_log is not None else [])
    clip_log = prefix_log + clip_log

    # NULL-coalesce, same pattern/rationale as `requested_cap_pct` above
    # (models.py:55-58): a pre-existing DB row predating this column's
    # migration reads NULL here too, despite the column's declared ORM
    # default (0.5).
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
    # coefficient computed above, per market_implied_risk_aversion's own
    # docstring: "Used both to build the Black-Litterman prior AND as
    # the quadratic-utility objective's risk-aversion parameter".

    # Per-sector inequality constraints live in their own list (rather
    # than being appended straight into advanced_constraints) because
    # the frontier sweep (sweep_efficient_frontier, below) also needs
    # them standalone: it prepends its own sum-to-one equality
    # constraint internally, so handing it advanced_constraints (which
    # already has one) would duplicate that equality constraint into
    # every one of the sweep's solves.
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
    suggested_weights = _solved_weights(result, initial, "max_sharpe", clip_log)
    suggested_return, suggested_vol, suggested_sharpe = portfolio_stats(suggested_weights, mu_bl, sigma_bl, risk_free_rate_pct)

    ticker_weights, max_sharpe_objective, suggested_sharpe_rounded = _build_ticker_weights_and_objective(
        "max_sharpe", tickers, current_weights_pct, current_dollar_by_ticker, total_value,
        suggested_weights, suggested_return, suggested_vol, suggested_sharpe,
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
    suggested_weights_utility = _solved_weights(utility_result, initial, "max_quadratic_utility", clip_log)
    suggested_return_utility, suggested_vol_utility, suggested_sharpe_utility = portfolio_stats(
        suggested_weights_utility, mu_bl, sigma_bl, risk_free_rate_pct,
    )
    # Reuses _build_ticker_weights_and_objective. Its ticker-weights/
    # rounded-sharpe return values aren't needed here: the top-level
    # OptimizationData.tickers/suggested_* fields stay tied to the
    # max_sharpe objective, and this objective's own tickers already
    # live inside max_utility_objective.tickers.
    _, max_utility_objective, _ = _build_ticker_weights_and_objective(
        "max_quadratic_utility", tickers, current_weights_pct, current_dollar_by_ticker, total_value,
        suggested_weights_utility, suggested_return_utility, suggested_vol_utility, suggested_sharpe_utility,
    )
    objectives = [max_sharpe_objective, max_utility_objective]

    # Efficient-frontier sweep: independent SLSQP solves at a range of
    # target volatilities spanning the achievable min-volatility
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

    # Random-portfolio backdrop cloud for the chart -- deliberately computed
    # from mu_bl/sigma_bl alone with NO bounds/sector_constraints (see
    # sample_random_portfolios' own docstring for why: it's meant to show
    # the full mathematically-reachable universe the position cap and
    # sector/ticker constraints cut down from, not another view of the same
    # constrained-feasible region frontier_points already covers).
    random_portfolios = sample_random_portfolios(mu_bl, sigma_bl, risk_free_rate_pct)

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
        random_portfolios=random_portfolios,
        sector_breakdown=sector_breakdown,
        clip_log=clip_log,
    )
