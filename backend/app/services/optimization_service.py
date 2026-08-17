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
mode (Black-Litterman return blending, sector/ticker constraints,
concentration penalty, efficient-frontier sweep) lands in Tasks 10-12.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from scipy.optimize import minimize
from sqlalchemy.orm import Session

from app.models import User
from app.risk_free_rate import get_cached_risk_free_rate
from app.services.investment_service import _investment_accounts
from app.services.portfolio_math_service import (
    TRADING_DAYS_PER_YEAR as LEDOIT_WOLF_ANNUALIZATION_DAYS,
    ledoit_wolf_shrinkage,
)
from app.services.price_matrix_service import (
    current_weights,
    held_tickers,
    portfolio_stats,
    price_matrix,
    priceable_tickers,
)
from app.services.sector_constraint_service import relax_position_cap_if_needed

TRADING_DAYS_PER_YEAR = 365
MIN_LOOKBACK_ROWS = 30
# Documented default for User.optimization_position_cap_pct (models.py). Used
# only as a fallback when the column reads NULL -- e.g. a pre-existing DB row
# from before this migration; see models.py:55-58. Its ORM `default=` only
# applies to newly-inserted rows, not ALTER TABLE-added columns on existing
# ones, so callers must coalesce NULL explicitly rather than trust the ORM
# default has taken effect.
DEFAULT_POSITION_CAP_PCT = 10.0


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
        # Built out in Tasks 10-12 (Black-Litterman blending, sector/ticker
        # constraints, concentration penalty, max-quadratic-utility
        # objective, efficient-frontier sweep). Stubbed here so basic mode
        # can ship and be tested independently -- see design doc decision 2.
        raise NotImplementedError("advanced mode lands in Task 10")

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

    ticker_weights = [
        TickerWeight(
            ticker=t,
            current_weight_pct=round(current_weights_pct[t], 2),
            suggested_weight_pct=round(float(suggested_weights[i]) * 100, 2),
        )
        for i, t in enumerate(tickers)
    ]
    suggested_sharpe_rounded = round(suggested_sharpe, 2) if suggested_sharpe is not None else None
    objectives = [
        ObjectiveResult(
            name="max_sharpe",
            tickers=ticker_weights,
            expected_return_pct=round(suggested_return, 2),
            volatility_pct=round(suggested_vol, 2),
            sharpe=suggested_sharpe_rounded,
        )
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
        advanced_enabled=False,
        position_cap_pct=round(effective_cap * 100, 2),
        cap_relaxed=cap_relax_log,
        objectives=objectives,
        frontier_points=None,
        sector_breakdown=None,
        clip_log=[],
    )
