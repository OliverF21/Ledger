"""
Optimization preferences + sector/ticker constraint CRUD, backing the
advanced Black-Litterman optimizer's user-configurable inputs (see
app/services/optimization_service.py):
- GET/PUT /investments/optimization-settings         : the three User.optimization_*
  preference columns (advanced_enabled, position_cap_pct, concentration_strength)
- GET/POST/PUT/DELETE /investments/sector-constraints[/{id}] : per-sector floor/cap
- GET/POST/PUT/DELETE /investments/ticker-constraints[/{id}] : per-ticker floor/cap

Mirrors routes/categories.py's CRUD shape: user_id == 1 scoping (single-user
desktop app), duplicate-check validation on create, updated_at bump on PUT
(via the model's onupdate=), and the same try/except
HTTPException-passthrough-then-log_and_raise convention.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import log_and_raise
from app.models import SectorConstraint, TickerConstraint, User

router = APIRouter(prefix="/investments", tags=["investments"])


# ─── Optimization settings (User.optimization_* preference columns) ──────────

# Documented defaults for User.optimization_position_cap_pct /
# optimization_concentration_strength (models.py:59-61) -- mirrors the
# constants of the same name/values in app/services/optimization_service.py.
# _ensure_columns()'s ALTER TABLE ADD COLUMN carries no DEFAULT clause, so
# these three columns land NULL (not their declared ORM default=) on any
# pre-existing DB row that predates the migration adding them -- see
# models.py:55-58. Callers must coalesce NULL to the documented default
# explicitly rather than trust the ORM default has taken effect.
DEFAULT_POSITION_CAP_PCT = 10.0
DEFAULT_CONCENTRATION_STRENGTH = 0.5


class OptimizationSettingsResponse(BaseModel):
    advanced_enabled: bool
    position_cap_pct: float
    concentration_strength: float


class OptimizationSettingsUpdate(BaseModel):
    advanced_enabled: bool | None = None
    position_cap_pct: float | None = None
    concentration_strength: float | None = None


def _settings_response(user: User) -> OptimizationSettingsResponse:
    """NULL-coalesce User's three optimization_* columns to their documented
    defaults before building the response -- see DEFAULT_POSITION_CAP_PCT's
    comment above and optimization_service.py's build_optimization_suggestion,
    which establishes this exact pattern. Without this, a pre-existing row
    with any of these three fields NULL would crash here: float(None) raises
    TypeError, and advanced_enabled=None fails OptimizationSettingsResponse's
    bool field validation. Shared by GET and PUT so both stay in sync -- PUT
    only overwrites fields the caller actually sent, so any field it didn't
    send can still be NULL when read back for the response."""
    return OptimizationSettingsResponse(
        advanced_enabled=(
            False if user.optimization_advanced_enabled is None else bool(user.optimization_advanced_enabled)
        ),
        position_cap_pct=(
            DEFAULT_POSITION_CAP_PCT if user.optimization_position_cap_pct is None
            else float(user.optimization_position_cap_pct)
        ),
        concentration_strength=(
            DEFAULT_CONCENTRATION_STRENGTH if user.optimization_concentration_strength is None
            else float(user.optimization_concentration_strength)
        ),
    )


@router.get("/optimization-settings", response_model=OptimizationSettingsResponse)
async def get_optimization_settings(db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=1).one()
    return _settings_response(user)


@router.put("/optimization-settings", response_model=OptimizationSettingsResponse)
async def update_optimization_settings(body: OptimizationSettingsUpdate, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter_by(id=1).one()
        if body.advanced_enabled is not None:
            user.optimization_advanced_enabled = body.advanced_enabled
        if body.position_cap_pct is not None:
            user.optimization_position_cap_pct = body.position_cap_pct
        if body.concentration_strength is not None:
            user.optimization_concentration_strength = body.concentration_strength
        db.commit()
        return _settings_response(user)
    except Exception as e:
        log_and_raise(e)


# ─── Sector constraints ────────────────────────────────────────────────────

class SectorConstraintPayload(BaseModel):
    sector: str
    floor_pct: float
    cap_pct: float


class SectorConstraintResponse(SectorConstraintPayload):
    id: int


@router.get("/sector-constraints", response_model=list[SectorConstraintResponse])
async def list_sector_constraints(db: Session = Depends(get_db)):
    rows = db.query(SectorConstraint).filter_by(user_id=1).all()
    return [
        SectorConstraintResponse(id=r.id, sector=r.sector, floor_pct=float(r.floor_pct), cap_pct=float(r.cap_pct))
        for r in rows
    ]


@router.post("/sector-constraints", response_model=SectorConstraintResponse)
async def create_sector_constraint(body: SectorConstraintPayload, db: Session = Depends(get_db)):
    try:
        existing = db.query(SectorConstraint).filter_by(user_id=1, sector=body.sector).one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail=f"Constraint for sector '{body.sector}' already exists")
        row = SectorConstraint(user_id=1, sector=body.sector, floor_pct=body.floor_pct, cap_pct=body.cap_pct)
        db.add(row)
        db.commit()
        return SectorConstraintResponse(id=row.id, sector=row.sector, floor_pct=float(row.floor_pct), cap_pct=float(row.cap_pct))
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)


@router.put("/sector-constraints/{constraint_id}", response_model=SectorConstraintResponse)
async def update_sector_constraint(constraint_id: int, body: SectorConstraintPayload, db: Session = Depends(get_db)):
    try:
        row = db.query(SectorConstraint).filter_by(id=constraint_id, user_id=1).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Sector constraint not found")
        row.floor_pct = body.floor_pct
        row.cap_pct = body.cap_pct
        db.commit()
        return SectorConstraintResponse(id=row.id, sector=row.sector, floor_pct=float(row.floor_pct), cap_pct=float(row.cap_pct))
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)


@router.delete("/sector-constraints/{constraint_id}")
async def delete_sector_constraint(constraint_id: int, db: Session = Depends(get_db)):
    try:
        row = db.query(SectorConstraint).filter_by(id=constraint_id, user_id=1).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Sector constraint not found")
        db.delete(row)
        db.commit()
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)


# ─── Ticker constraints ─────────────────────────────────────────────────────
# Direct mirror of the SectorConstraint block above: same validation shape,
# same user_id == 1 scoping, same HTTPException conventions -- substituting
# `sector: str` for `ticker: str` and SectorConstraint for TickerConstraint.

class TickerConstraintPayload(BaseModel):
    ticker: str
    floor_pct: float
    cap_pct: float


class TickerConstraintResponse(TickerConstraintPayload):
    id: int


@router.get("/ticker-constraints", response_model=list[TickerConstraintResponse])
async def list_ticker_constraints(db: Session = Depends(get_db)):
    rows = db.query(TickerConstraint).filter_by(user_id=1).all()
    return [
        TickerConstraintResponse(id=r.id, ticker=r.ticker, floor_pct=float(r.floor_pct), cap_pct=float(r.cap_pct))
        for r in rows
    ]


@router.post("/ticker-constraints", response_model=TickerConstraintResponse)
async def create_ticker_constraint(body: TickerConstraintPayload, db: Session = Depends(get_db)):
    try:
        existing = db.query(TickerConstraint).filter_by(user_id=1, ticker=body.ticker).one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail=f"Constraint for ticker '{body.ticker}' already exists")
        row = TickerConstraint(user_id=1, ticker=body.ticker, floor_pct=body.floor_pct, cap_pct=body.cap_pct)
        db.add(row)
        db.commit()
        return TickerConstraintResponse(id=row.id, ticker=row.ticker, floor_pct=float(row.floor_pct), cap_pct=float(row.cap_pct))
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)


@router.put("/ticker-constraints/{constraint_id}", response_model=TickerConstraintResponse)
async def update_ticker_constraint(constraint_id: int, body: TickerConstraintPayload, db: Session = Depends(get_db)):
    try:
        row = db.query(TickerConstraint).filter_by(id=constraint_id, user_id=1).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Ticker constraint not found")
        row.floor_pct = body.floor_pct
        row.cap_pct = body.cap_pct
        db.commit()
        return TickerConstraintResponse(id=row.id, ticker=row.ticker, floor_pct=float(row.floor_pct), cap_pct=float(row.cap_pct))
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)


@router.delete("/ticker-constraints/{constraint_id}")
async def delete_ticker_constraint(constraint_id: int, db: Session = Depends(get_db)):
    try:
        row = db.query(TickerConstraint).filter_by(id=constraint_id, user_id=1).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Ticker constraint not found")
        db.delete(row)
        db.commit()
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)
