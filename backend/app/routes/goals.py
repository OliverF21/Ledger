"""Financial goals CRUD and labeled-transfer progress."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.budgets_db import get_budgets_db
from app.database import get_db
from app.errors import log_and_raise
from app.services.goals_service import (
    GOAL_KIND_LABELS,
    build_goal_progress,
    get_goal,
    list_goal_progress,
    upsert_goal,
)

router = APIRouter(prefix="/goals", tags=["goals"])


class GoalOut(BaseModel):
    id: int
    name: str
    kind: str
    kind_label: str
    target_amount: float
    opening_amount: float
    labeled_in: float
    labeled_out: float
    progress: float
    remaining: float
    monthly_contribution: float | None = None
    annual_return: float
    target_date: str | None = None
    status: str
    color: str
    months_remaining: int | None = None
    months_exact: float | None = None
    projected_end_month: str | None = None
    percent_funded: float


class GoalListResponse(BaseModel):
    goals: list[GoalOut]


class GoalWrite(BaseModel):
    name: str = Field(..., min_length=1)
    kind: str = "custom"
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(0, ge=0)
    target_date: Optional[str] = None
    monthly_contribution: Optional[float] = Field(None, ge=0)
    annual_return_assumption: Optional[float] = Field(None, ge=0, le=0.12)
    status: str = "active"
    color: Optional[str] = None


def _to_out(item) -> GoalOut:
    return GoalOut(
        id=item.id,
        name=item.name,
        kind=item.kind,
        kind_label=GOAL_KIND_LABELS.get(item.kind, item.kind),
        target_amount=item.target_amount,
        opening_amount=item.opening_amount,
        labeled_in=item.labeled_in,
        labeled_out=item.labeled_out,
        progress=item.progress,
        remaining=item.remaining,
        monthly_contribution=item.monthly_contribution,
        annual_return=item.annual_return,
        target_date=item.target_date,
        status=item.status,
        color=item.color,
        months_remaining=item.months_remaining,
        months_exact=item.months_exact,
        projected_end_month=item.projected_end_month,
        percent_funded=item.percent_funded,
    )


@router.get("", response_model=GoalListResponse)
def list_goals(
    bdb: Session = Depends(get_budgets_db),
    ldb: Session = Depends(get_db),
):
    try:
        return GoalListResponse(goals=[_to_out(g) for g in list_goal_progress(bdb, ldb)])
    except Exception as e:
        log_and_raise(e)


@router.post("", response_model=GoalOut)
def create_goal(
    req: GoalWrite,
    bdb: Session = Depends(get_budgets_db),
    ldb: Session = Depends(get_db),
):
    try:
        goal, _, _ = upsert_goal(
            bdb,
            name=req.name,
            kind=req.kind,
            target_amount=req.target_amount,
            current_amount=req.current_amount,
            target_date=req.target_date,
            monthly_contribution=req.monthly_contribution,
            annual_return_assumption=req.annual_return_assumption,
            status=req.status,
            color=req.color,
        )
        bdb.commit()
        bdb.refresh(goal)
        return _to_out(build_goal_progress(goal, ldb))
    except ValueError as e:
        bdb.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        bdb.rollback()
        log_and_raise(e)


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: int,
    req: GoalWrite,
    bdb: Session = Depends(get_budgets_db),
    ldb: Session = Depends(get_db),
):
    try:
        goal, _, _ = upsert_goal(
            bdb,
            goal_id=goal_id,
            name=req.name,
            kind=req.kind,
            target_amount=req.target_amount,
            current_amount=req.current_amount,
            target_date=req.target_date,
            monthly_contribution=req.monthly_contribution,
            annual_return_assumption=req.annual_return_assumption,
            status=req.status,
            color=req.color,
        )
        bdb.commit()
        bdb.refresh(goal)
        return _to_out(build_goal_progress(goal, ldb))
    except ValueError as e:
        bdb.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        bdb.rollback()
        log_and_raise(e)


@router.delete("/{goal_id}")
def dismiss_goal(goal_id: int, bdb: Session = Depends(get_budgets_db)):
    try:
        goal = get_goal(bdb, goal_id)
        goal.status = "dismissed"
        bdb.commit()
        return {"success": True, "id": goal_id, "status": "dismissed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        bdb.rollback()
        log_and_raise(e)
