"""
Portfolio risk & performance metrics + optimization suggestion, built on top
of app.services.risk_service / app.services.optimization_service. Kept
separate from routes/investments.py since it's a distinct analytical surface
(numpy/scipy-backed) rather than direct Plaid-holdings CRUD.
- GET /investments/risk/metrics  : volatility, Sharpe, VaR, max drawdown, beta, TWR/XIRR/CAGR
- GET /investments/risk/optimize : suggested max-Sharpe allocation vs. current (Task 10)
- POST /investments/risk/optimize: the same, under user-set position / sector /
  ticker constraints, optionally with the efficient frontier and a reference
  cloud of random portfolios (the Advanced optimization panel)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import log_and_raise
from app.services.risk_service import build_risk_metrics
from app.services.optimization_service import (
    build_optimization_suggestion,
    OptimizerConstraints,
    SP500_SECTOR_WEIGHTS,
)

router = APIRouter(prefix="/investments/risk", tags=["investments"])


class VarHorizonResponse(BaseModel):
    days: int
    var_95_pct: Optional[float]
    var_95_dollar: Optional[float]
    var_99_pct: Optional[float]
    var_99_dollar: Optional[float]


class RiskMetricsResponse(BaseModel):
    lookback_days: int
    as_of: str
    volatility_pct: Optional[float]
    sharpe_ratio: Optional[float]
    max_drawdown_pct: Optional[float]
    drawdown_duration_days: Optional[int]
    beta_vs_spy: Optional[float]
    cagr_pct: Optional[float]
    twr_pct: Optional[float]
    mwr_pct: Optional[float]
    risk_free_rate_pct: float
    data_points: int
    # VaR — independent backtest of current holdings, see risk_service.py
    var_horizons: list[VarHorizonResponse]
    var_data_points: int
    var_excluded_tickers: list[str]
    var_coverage_pct: Optional[float]
    portfolio_value_used: Optional[float]


@router.get("/metrics", response_model=RiskMetricsResponse)
async def get_risk_metrics(lookback_days: int = Query(365, ge=30, le=1825), db: Session = Depends(get_db)):
    try:
        data = build_risk_metrics(db, lookback_days=lookback_days)
        return RiskMetricsResponse(
            **{k: v for k, v in vars(data).items() if k != "var_horizons"},
            var_horizons=[VarHorizonResponse(**vars(h)) for h in data.var_horizons],
        )
    except Exception as e:
        log_and_raise(e)


class AllocationWeight(BaseModel):
    ticker: str
    current_weight_pct: float
    suggested_weight_pct: float


class RiskReturnPointResponse(BaseModel):
    volatility_pct: float
    return_pct: float
    sharpe: Optional[float] = None


class SectorRefResponse(BaseModel):
    name: str
    current_weight_pct: float
    sp_reference_pct: Optional[float]


class OptimizationResponse(BaseModel):
    tickers: list[AllocationWeight]
    current_expected_return_pct: Optional[float]
    current_volatility_pct: Optional[float]
    current_sharpe: Optional[float]
    suggested_expected_return_pct: Optional[float]
    suggested_volatility_pct: Optional[float]
    suggested_sharpe: Optional[float]
    data_points: int
    insufficient_data: bool
    frontier: list[RiskReturnPointResponse] = []
    scatter: list[RiskReturnPointResponse] = []
    current_point: Optional[RiskReturnPointResponse] = None
    max_sharpe_point: Optional[RiskReturnPointResponse] = None
    max_utility_point: Optional[RiskReturnPointResponse] = None
    sectors: list[SectorRefResponse] = []
    ticker_sectors: dict[str, str] = {}
    infeasible: bool = False


class BoundRequest(BaseModel):
    """A floor/cap pair in percent. Floor above cap is clamped downstream
    rather than rejected — the sliders can cross while being dragged."""
    floor_pct: float = Field(0, ge=0, le=100)
    cap_pct: float = Field(100, ge=0, le=100)


class OptimizeRequest(BaseModel):
    lookback_days: int = Field(365, ge=90, le=1825)
    position_cap_pct: float = Field(100, ge=1, le=100)
    diversification_pct: float = Field(0, ge=0, le=100)
    sector_bounds: dict[str, BoundRequest] = {}
    ticker_bounds: dict[str, BoundRequest] = {}
    include_frontier: bool = True


def _to_response(data) -> OptimizationResponse:
    def point(p):
        return RiskReturnPointResponse(**vars(p)) if p is not None else None

    return OptimizationResponse(
        tickers=[AllocationWeight(**vars(w)) for w in data.tickers],
        current_expected_return_pct=data.current_expected_return_pct,
        current_volatility_pct=data.current_volatility_pct,
        current_sharpe=data.current_sharpe,
        suggested_expected_return_pct=data.suggested_expected_return_pct,
        suggested_volatility_pct=data.suggested_volatility_pct,
        suggested_sharpe=data.suggested_sharpe,
        data_points=data.data_points,
        insufficient_data=data.insufficient_data,
        frontier=[RiskReturnPointResponse(**vars(p)) for p in data.frontier],
        scatter=[RiskReturnPointResponse(**vars(p)) for p in data.scatter],
        current_point=point(data.current_point),
        max_sharpe_point=point(data.max_sharpe_point),
        max_utility_point=point(data.max_utility_point),
        sectors=[SectorRefResponse(**vars(s)) for s in data.sectors],
        ticker_sectors=data.ticker_sectors,
        infeasible=data.infeasible,
    )


@router.get("/optimize", response_model=OptimizationResponse)
async def get_optimization(lookback_days: int = Query(365, ge=90, le=1825), db: Session = Depends(get_db)):
    """Unconstrained max-Sharpe suggestion — the cheap path the Investments
    summary uses. No frontier sweep."""
    try:
        return _to_response(build_optimization_suggestion(db, lookback_days=lookback_days))
    except Exception as e:
        log_and_raise(e)


@router.post("/optimize", response_model=OptimizationResponse)
async def run_optimization(body: OptimizeRequest, db: Session = Depends(get_db)):
    """Run the optimizer under the panel's constraints, with the frontier."""
    try:
        constraints = OptimizerConstraints(
            position_cap_pct=body.position_cap_pct,
            diversification_pct=body.diversification_pct,
            sector_bounds={k: (v.floor_pct, v.cap_pct) for k, v in body.sector_bounds.items()},
            ticker_bounds={k: (v.floor_pct, v.cap_pct) for k, v in body.ticker_bounds.items()},
        )
        return _to_response(build_optimization_suggestion(
            db,
            lookback_days=body.lookback_days,
            constraints=constraints,
            include_frontier=body.include_frontier,
        ))
    except Exception as e:
        log_and_raise(e)


@router.get("/sector-reference")
async def get_sector_reference():
    """Approximate S&P 500 sector weights, shown as reference marks beside the
    sector sliders."""
    return {"weights": SP500_SECTOR_WEIGHTS}
