# backend/app/services/optimization_service.py
"""
Suggested max-Sharpe portfolio allocation across currently-held tickers, using
a mean-variance optimizer (scipy SLSQP rather than PyPortfolioOpt/cvxpy — see
plan doc for why: cvxpy's solver backends are a known headache to bundle into
the PyInstaller desktop build, and SLSQP is more than sufficient for this
book's size, ~5-30 holdings).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from scipy.optimize import minimize
from sqlalchemy.orm import Session

from app.models import Holding, MarketPrice, Security
from app.price_provider import fetch_sectors
from app.risk_free_rate import get_cached_risk_free_rate
from app.services.investment_service import (
    _investment_accounts,
    account_gross_holdings,
    scaled_holding_market_value,
)

TRADING_DAYS_PER_YEAR = 365
MIN_LOOKBACK_ROWS = 30

# Points sampled along the frontier, and random portfolios in the reference
# cloud. Both are drawn, not read, so they're sized for legibility rather than
# precision — 40 points already renders as a smooth curve.
FRONTIER_POINTS = 40
SCATTER_POINTS = 600

# Approximate S&P 500 sector weights, shown next to each sector slider purely
# as a reference mark. Rounded and updated by hand; nothing computes from them,
# so drift costs a slightly stale label and nothing else.
SP500_SECTOR_WEIGHTS: dict[str, float] = {
    "Technology": 32.0,
    "Financial Services": 14.0,
    "Healthcare": 10.0,
    "Consumer Cyclical": 10.0,
    "Communication Services": 9.0,
    "Industrials": 8.0,
    "Consumer Defensive": 6.0,
    "Energy": 4.0,
    "Utilities": 2.5,
    "Real Estate": 2.0,
    "Basic Materials": 2.0,
}

UNCLASSIFIED_SECTOR = "Unclassified"


@dataclass(frozen=True)
class TickerWeight:
    ticker: str
    current_weight_pct: float
    suggested_weight_pct: float


@dataclass(frozen=True)
class RiskReturnPoint:
    """One portfolio placed on the risk/return plane, in annualised percent."""
    volatility_pct: float
    return_pct: float
    sharpe: float | None = None


@dataclass(frozen=True)
class SectorRef:
    """A sector present in the book, with the weight currently allocated to it
    and an approximate S&P 500 weight to compare against."""
    name: str
    current_weight_pct: float
    sp_reference_pct: float | None


@dataclass(frozen=True)
class OptimizerConstraints:
    """
    User-set bounds from the Advanced optimization panel. All percentages.

    `diversification` is not a bound but a preference: it blends the objective
    from pure max-Sharpe (0) toward equal weight (100) with a quadratic penalty
    on the distance from 1/n. Expressing "spread it out" as a penalty rather
    than a hard constraint keeps the problem feasible at every slider position,
    which a min-weight floor would not.
    """
    position_cap_pct: float = 100.0
    diversification_pct: float = 0.0
    sector_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    ticker_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)


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
    # Advanced-optimization payload. Empty on the unconstrained default call so
    # the cheap summary path doesn't pay for a frontier sweep it won't draw.
    frontier: list[RiskReturnPoint] = field(default_factory=list)
    scatter: list[RiskReturnPoint] = field(default_factory=list)
    current_point: RiskReturnPoint | None = None
    max_sharpe_point: RiskReturnPoint | None = None
    max_utility_point: RiskReturnPoint | None = None
    sectors: list[SectorRef] = field(default_factory=list)
    ticker_sectors: dict[str, str] = field(default_factory=dict)
    infeasible: bool = False


def _empty_result(data_points: int = 0) -> OptimizationData:
    return OptimizationData(
        tickers=[], current_expected_return_pct=None, current_volatility_pct=None, current_sharpe=None,
        suggested_expected_return_pct=None, suggested_volatility_pct=None, suggested_sharpe=None,
        data_points=data_points, insufficient_data=True,
    )


def _priceable_tickers(db: Session, tickers: list[str], start: date, end: date) -> list[str]:
    """Held tickers that have at least one MarketPrice row in the lookback
    window. A single ticker yfinance can't resolve (money-market funds,
    unusual symbols) shouldn't disable optimization for the rest of the
    book — drop it here so `tickers` only contains names `_price_matrix` can
    actually use."""
    if not tickers:
        return []
    rows = (
        db.query(MarketPrice.ticker)
        .filter(MarketPrice.ticker.in_(tickers), MarketPrice.price_date >= start, MarketPrice.price_date <= end)
        .distinct()
        .all()
    )
    priceable = {row[0] for row in rows}
    return [t for t in tickers if t in priceable]


def _held_tickers(db: Session, account_ids: list[int]) -> list[str]:
    if not account_ids:
        return []
    rows = (
        db.query(Security.ticker_symbol)
        .join(Holding, Holding.security_id == Security.id)
        .filter(
            Holding.account_id.in_(account_ids),
            Security.ticker_symbol.isnot(None),
            Security.is_cash_equivalent.is_(False),
        )
        .distinct()
        .all()
    )
    return sorted({row[0] for row in rows if row[0]})


def _price_matrix(db: Session, tickers: list[str], start: date, end: date) -> tuple[list[date], np.ndarray]:
    """Rows = dates common to every ticker, columns = tickers (in `tickers` order)."""
    rows = (
        db.query(MarketPrice.ticker, MarketPrice.price_date, MarketPrice.close_price)
        .filter(MarketPrice.ticker.in_(tickers), MarketPrice.price_date >= start, MarketPrice.price_date <= end)
        .all()
    )
    by_ticker: dict[str, dict[date, float]] = {t: {} for t in tickers}
    for ticker, price_date, close_price in rows:
        by_ticker[ticker][price_date] = float(close_price)

    if not all(by_ticker.values()):
        return [], np.array([])
    common_dates = sorted(set.intersection(*(set(d.keys()) for d in by_ticker.values())))
    if not common_dates:
        return [], np.array([])

    matrix = np.array([[by_ticker[t][d] for t in tickers] for d in common_dates])
    return common_dates, matrix


def _current_weights(db: Session, account_ids: list[int], tickers: list[str]) -> dict[str, float]:
    accounts_by_id = {a.id: a for a in _investment_accounts(db) if a.id in account_ids}
    holdings = (
        db.query(Holding)
        .join(Security)
        .filter(Holding.account_id.in_(account_ids), Security.ticker_symbol.in_(tickers))
        .all()
        if account_ids else []
    )
    gross_by_account = account_gross_holdings(holdings)
    value_by_ticker: dict[str, float] = {t: 0.0 for t in tickers}
    for h in holdings:
        value = scaled_holding_market_value(h, accounts_by_id[h.account_id], gross_by_account)
        value_by_ticker[h.security.ticker_symbol] += value
    total = sum(value_by_ticker.values())
    if total <= 0:
        return {t: 0.0 for t in tickers}
    return {t: v / total * 100 for t, v in value_by_ticker.items()}


def _sectors_for(db: Session, tickers: list[str]) -> dict[str, str]:
    """
    Sector per ticker, backfilling any that are still NULL from the market-data
    provider and persisting the result. Runs once per new holding; anything the
    provider can't classify is pinned to UNCLASSIFIED_SECTOR so it stops being
    retried on every call.
    """
    if not tickers:
        return {}

    rows = (
        db.query(Security.ticker_symbol, Security.sector)
        .filter(Security.ticker_symbol.in_(tickers))
        .all()
    )
    known = {t: s for t, s in rows if t}
    missing = [t for t in tickers if not known.get(t)]

    if missing:
        try:
            fetched = fetch_sectors(missing)
        except Exception:
            fetched = {}
        for ticker in missing:
            sector = fetched.get(ticker) or UNCLASSIFIED_SECTOR
            known[ticker] = sector
            db.query(Security).filter(Security.ticker_symbol == ticker).update(
                {Security.sector: sector}, synchronize_session=False
            )
        db.commit()

    return {t: known.get(t) or UNCLASSIFIED_SECTOR for t in tickers}


def _bounds(tickers: list[str], constraints: OptimizerConstraints) -> list[tuple[float, float]]:
    """
    Per-ticker (low, high) weight bounds as fractions. A ticker's own cap
    overrides the global position cap — that's what the panel's copy promises —
    and a floor above its cap is clamped rather than handed to SLSQP, which
    would just report the problem infeasible.
    """
    global_cap = max(0.0, min(100.0, constraints.position_cap_pct)) / 100
    bounds: list[tuple[float, float]] = []
    for ticker in tickers:
        floor_pct, cap_pct = constraints.ticker_bounds.get(ticker, (0.0, None))
        low = max(0.0, min(100.0, floor_pct)) / 100
        high = global_cap if cap_pct is None else max(0.0, min(100.0, cap_pct)) / 100
        bounds.append((low, max(low, high)))
    return bounds


def _sector_constraint_defs(
    tickers: list[str],
    ticker_sectors: dict[str, str],
    constraints: OptimizerConstraints,
) -> list[dict]:
    """Linear inequality constraints holding each sector's summed weight
    between its floor and cap."""
    defs: list[dict] = []
    for sector, (floor_pct, cap_pct) in constraints.sector_bounds.items():
        idx = [i for i, t in enumerate(tickers) if ticker_sectors.get(t) == sector]
        if not idx:
            continue
        mask = np.zeros(len(tickers))
        mask[idx] = 1.0
        floor = max(0.0, min(100.0, floor_pct)) / 100
        cap = max(floor, min(100.0, cap_pct) / 100)
        # Bound as f(w) >= 0 both ways, which is what SLSQP's "ineq" expects.
        defs.append({"type": "ineq", "fun": (lambda w, m=mask, f=floor: float(m @ w) - f)})
        defs.append({"type": "ineq", "fun": (lambda w, m=mask, c=cap: c - float(m @ w))})
    return defs


def _feasible_start(bounds: list[tuple[float, float]]) -> np.ndarray:
    """
    Starting point that already satisfies the bounds and sums to 1. Handing
    SLSQP a start outside its own bounds is the most common way to get a
    spurious "infeasible" back.
    """
    n = len(bounds)
    lows = np.array([b[0] for b in bounds])
    highs = np.array([b[1] for b in bounds])
    weights = lows.copy()
    remaining = 1.0 - weights.sum()
    if remaining > 0:
        headroom = highs - lows
        total_headroom = headroom.sum()
        if total_headroom > 0:
            weights = weights + headroom * (min(remaining, total_headroom) / total_headroom)
    total = weights.sum()
    return weights / total if total > 0 else np.array([1.0 / n] * n)


def _solve(
    objective,
    bounds: list[tuple[float, float]],
    extra_constraints: list[dict],
    extra_eq=None,
) -> np.ndarray | None:
    """SLSQP with the fully-invested equality always present. Returns None when
    the solver can't satisfy the constraints, so callers can report an
    infeasible constraint set rather than silently drawing a wrong answer."""
    cons: list[dict] = [{"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0}]
    cons.extend(extra_constraints)
    if extra_eq is not None:
        cons.append(extra_eq)
    result = minimize(
        objective, _feasible_start(bounds), method="SLSQP",
        bounds=bounds, constraints=cons, options={"maxiter": 300, "ftol": 1e-9},
    )
    if not result.success:
        return None
    weights = np.clip(result.x, 0, None)
    total = weights.sum()
    return weights / total if total > 0 else None


def _portfolio_stats(
    weights: np.ndarray, mean_returns: np.ndarray, cov: np.ndarray, risk_free_rate_pct: float
) -> tuple[float, float, float | None]:
    expected_return = float(np.dot(weights, mean_returns)) * TRADING_DAYS_PER_YEAR
    volatility = float(np.sqrt(weights @ cov @ weights)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (expected_return - risk_free_rate_pct / 100) / volatility if volatility > 0 else None
    return expected_return * 100, volatility * 100, sharpe


def _stats_point(
    weights: np.ndarray, mean_returns: np.ndarray, cov: np.ndarray, rf_pct: float
) -> RiskReturnPoint:
    ret, vol, sharpe = _portfolio_stats(weights, mean_returns, cov, rf_pct)
    # Cast off numpy scalars — they serialise inconsistently and leak dtype
    # noise into the API response.
    return RiskReturnPoint(
        volatility_pct=round(float(vol), 2),
        return_pct=round(float(ret), 2),
        sharpe=round(float(sharpe), 2) if sharpe is not None else None,
    )


def _build_frontier(
    mean_returns: np.ndarray,
    cov: np.ndarray,
    bounds: list[tuple[float, float]],
    sector_cons: list[dict],
    rf_pct: float,
) -> list[RiskReturnPoint]:
    """
    The efficient frontier under the user's constraints: for a grid of target
    returns, the minimum-variance portfolio achieving that return. Targets the
    constraints make unreachable simply drop out, so a tight cap shortens the
    curve instead of breaking it.
    """
    annual_mu = mean_returns * TRADING_DAYS_PER_YEAR

    def variance(w: np.ndarray) -> float:
        return float(w @ cov @ w)

    # Span the achievable return range rather than the raw asset range: with a
    # position cap you often can't reach the best single asset's return.
    lo_w = _solve(variance, bounds, sector_cons)
    hi_w = _solve(lambda w: -float(np.dot(w, annual_mu)), bounds, sector_cons)
    if lo_w is None or hi_w is None:
        return []
    lo_ret = float(np.dot(lo_w, annual_mu))
    hi_ret = float(np.dot(hi_w, annual_mu))
    if hi_ret <= lo_ret:
        return [_stats_point(lo_w, mean_returns, cov, rf_pct)]

    points: list[RiskReturnPoint] = []
    for i in range(FRONTIER_POINTS):
        target = lo_ret + (hi_ret - lo_ret) * i / (FRONTIER_POINTS - 1)
        weights = _solve(
            variance, bounds, sector_cons,
            extra_eq={"type": "eq", "fun": (lambda w, t=target: float(np.dot(w, annual_mu)) - t)},
        )
        if weights is not None:
            points.append(_stats_point(weights, mean_returns, cov, rf_pct))

    points.sort(key=lambda pt: pt.volatility_pct)
    return points


def _random_scatter(mean_returns: np.ndarray, cov: np.ndarray, rf_pct: float) -> list[RiskReturnPoint]:
    """
    A cloud of random fully-invested portfolios, drawn only to give the frontier
    a sense of scale. Deliberately ignores the user's constraints — that's what
    makes the frontier's position against it meaningful — and is seeded so the
    cloud doesn't reshuffle on every slider nudge.
    """
    rng = np.random.default_rng(20240827)
    n = len(mean_returns)
    weights = rng.dirichlet(np.ones(n), size=SCATTER_POINTS)
    annual_mu = mean_returns * TRADING_DAYS_PER_YEAR
    rets = weights @ annual_mu * 100
    vols = np.sqrt(np.einsum("ij,jk,ik->i", weights, cov, weights)) * np.sqrt(TRADING_DAYS_PER_YEAR) * 100
    return [
        RiskReturnPoint(volatility_pct=round(float(v), 2), return_pct=round(float(r), 2))
        for v, r in zip(vols, rets)
    ]


def build_optimization_suggestion(
    db: Session,
    *,
    lookback_days: int = 365,
    constraints: OptimizerConstraints | None = None,
    include_frontier: bool = False,
) -> OptimizationData:
    """
    Max-Sharpe suggestion for the current book. With `constraints` it honours
    position caps and per-sector / per-ticker floors and caps; with
    `include_frontier` it also returns the constrained efficient frontier, the
    max-quadratic-utility portfolio and a reference cloud of random portfolios.

    The frontier sweep is ~40 extra SLSQP solves, so it stays opt-in — the
    Investments summary renders without it.
    """
    constraints = constraints or OptimizerConstraints()
    lookback_days = max(90, min(int(lookback_days), 1825))
    end = date.today()
    start = end - timedelta(days=lookback_days)

    accounts = _investment_accounts(db)
    account_ids = [a.id for a in accounts]
    tickers = _held_tickers(db, account_ids)
    if len(tickers) < 2:
        return _empty_result()

    tickers = _priceable_tickers(db, tickers, start, end)
    if len(tickers) < 2:
        return _empty_result()

    dates, prices = _price_matrix(db, tickers, start, end)
    if len(dates) < MIN_LOOKBACK_ROWS:
        return _empty_result(data_points=len(dates))

    returns = prices[1:] / prices[:-1] - 1
    mean_returns = returns.mean(axis=0)
    cov = np.cov(returns, rowvar=False)
    risk_free_rate_pct = get_cached_risk_free_rate(db)

    current_weights_pct = _current_weights(db, account_ids, tickers)
    current_weights = np.array([current_weights_pct[t] / 100 for t in tickers])
    current_point = _stats_point(current_weights, mean_returns, cov, risk_free_rate_pct)

    ticker_sectors = _sectors_for(db, tickers) if (constraints.sector_bounds or include_frontier) else {}
    bounds = _bounds(tickers, constraints)
    sector_cons = _sector_constraint_defs(tickers, ticker_sectors, constraints)

    n = len(tickers)
    equal_weight = np.array([1.0 / n] * n)
    # Slider 0 leaves the objective untouched; slider 100 pulls hard enough that
    # the solution sits essentially at equal weight.
    spread_lambda = (max(0.0, min(100.0, constraints.diversification_pct)) / 100) ** 2 * 12.0

    def neg_sharpe(weights: np.ndarray) -> float:
        ret = float(np.dot(weights, mean_returns)) * TRADING_DAYS_PER_YEAR
        vol = float(np.sqrt(weights @ cov @ weights)) * np.sqrt(TRADING_DAYS_PER_YEAR)
        if vol == 0:
            return 0.0
        penalty = spread_lambda * float(np.sum((weights - equal_weight) ** 2))
        return -(ret - risk_free_rate_pct / 100) / vol + penalty

    suggested_weights = _solve(neg_sharpe, bounds, sector_cons)
    infeasible = suggested_weights is None
    if suggested_weights is None:
        suggested_weights = _feasible_start(bounds)

    suggested_point = _stats_point(suggested_weights, mean_returns, cov, risk_free_rate_pct)

    ticker_weights = [
        TickerWeight(
            ticker=t,
            current_weight_pct=round(current_weights_pct[t], 2),
            suggested_weight_pct=round(float(suggested_weights[i]) * 100, 2),
        )
        for i, t in enumerate(tickers)
    ]

    frontier: list[RiskReturnPoint] = []
    scatter: list[RiskReturnPoint] = []
    max_utility_point: RiskReturnPoint | None = None
    sectors: list[SectorRef] = []

    if include_frontier:
        frontier = _build_frontier(mean_returns, cov, bounds, sector_cons, risk_free_rate_pct)
        scatter = _random_scatter(mean_returns, cov, risk_free_rate_pct)

        # Max quadratic utility: return minus a risk charge. The standard
        # textbook risk-aversion of 1 on annualised variance; it lands to the
        # right of max-Sharpe on the frontier, which is the point of showing it.
        annual_mu = mean_returns * TRADING_DAYS_PER_YEAR

        def neg_utility(weights: np.ndarray) -> float:
            ret = float(np.dot(weights, annual_mu))
            var = float(weights @ cov @ weights) * TRADING_DAYS_PER_YEAR
            return -(ret - 0.5 * var)

        utility_weights = _solve(neg_utility, bounds, sector_cons)
        if utility_weights is not None:
            max_utility_point = _stats_point(utility_weights, mean_returns, cov, risk_free_rate_pct)

        by_sector: dict[str, float] = {}
        for ticker in tickers:
            by_sector[ticker_sectors.get(ticker, UNCLASSIFIED_SECTOR)] = (
                by_sector.get(ticker_sectors.get(ticker, UNCLASSIFIED_SECTOR), 0.0)
                + current_weights_pct[ticker]
            )
        sectors = [
            SectorRef(
                name=name,
                current_weight_pct=round(weight, 2),
                sp_reference_pct=SP500_SECTOR_WEIGHTS.get(name),
            )
            for name, weight in sorted(by_sector.items(), key=lambda kv: -kv[1])
        ]

    return OptimizationData(
        tickers=ticker_weights,
        current_expected_return_pct=current_point.return_pct,
        current_volatility_pct=current_point.volatility_pct,
        current_sharpe=current_point.sharpe,
        suggested_expected_return_pct=suggested_point.return_pct,
        suggested_volatility_pct=suggested_point.volatility_pct,
        suggested_sharpe=suggested_point.sharpe,
        data_points=len(dates),
        insufficient_data=False,
        frontier=frontier,
        scatter=scatter,
        current_point=current_point,
        max_sharpe_point=suggested_point,
        max_utility_point=max_utility_point,
        sectors=sectors,
        ticker_sectors=ticker_sectors,
        infeasible=infeasible,
    )
