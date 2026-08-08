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
