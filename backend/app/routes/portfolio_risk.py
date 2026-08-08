"""
Portfolio risk & performance metrics + optimization suggestion, built on top
of app.services.risk_service / app.services.optimization_service. Kept
separate from routes/investments.py since it's a distinct analytical surface
(numpy/scipy-backed) rather than direct Plaid-holdings CRUD.
- GET /investments/risk/metrics  : volatility, Sharpe, VaR, max drawdown, beta, TWR/XIRR/CAGR
- GET /investments/risk/optimize : suggested max-Sharpe allocation vs. current (Task 10)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import log_and_raise
from app.services.risk_service import build_risk_metrics
from app.services.optimization_service import build_optimization_suggestion

router = APIRouter(prefix="/investments/risk", tags=["investments"])


class RiskMetricsResponse(BaseModel):
    lookback_days: int
    as_of: str
    volatility_pct: Optional[float]
    sharpe_ratio: Optional[float]
    var_95_pct: Optional[float]
    var_99_pct: Optional[float]
    max_drawdown_pct: Optional[float]
    drawdown_duration_days: Optional[int]
    beta_vs_spy: Optional[float]
    cagr_pct: Optional[float]
    twr_pct: Optional[float]
    mwr_pct: Optional[float]
    risk_free_rate_pct: float
    data_points: int


@router.get("/metrics", response_model=RiskMetricsResponse)
async def get_risk_metrics(lookback_days: int = Query(365, ge=30, le=1825), db: Session = Depends(get_db)):
    try:
        data = build_risk_metrics(db, lookback_days=lookback_days)
        return RiskMetricsResponse(**vars(data))
    except Exception as e:
        log_and_raise(e)


class AllocationWeight(BaseModel):
    ticker: str
    current_weight_pct: float
    suggested_weight_pct: float


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


@router.get("/optimize", response_model=OptimizationResponse)
async def get_optimization(lookback_days: int = Query(365, ge=90, le=1825), db: Session = Depends(get_db)):
    try:
        data = build_optimization_suggestion(db, lookback_days=lookback_days)
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
        )
    except Exception as e:
        log_and_raise(e)
