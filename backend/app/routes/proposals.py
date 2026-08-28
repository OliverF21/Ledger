"""
AI advisor proposal endpoints.

A proposal is an AI-generated *intent* (created by the MCP server's propose_*
tools) staged in the `proposals` table of budgets.db. It has NO effect on real
data until the user applies it in the Advisor page.

Auth split (deliberate — this is the trust boundary):
- POST /proposals              → require_proposal_service (MCP create-only key)
- GET  /proposals              → require_auth (user session)
- POST /proposals/{id}/apply   → require_auth  ← the ONLY route that mutates
- POST /proposals/{id}/dismiss → require_auth
- POST /proposals/{id}/undo    → require_auth

The MCP server can only ever CREATE pending proposals. Applying, dismissing, and
undoing require the user's browser session — Claude cannot do them.

Supported kinds: set_budget, set_goal, update_goal_contribution, attribute_transfer.
There is no set_savings_budget — spend budgets stay spend caps.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analytics_shared import KNOWN_CATEGORY_KEYS, display_label_for_key
from app.auth import require_auth, require_proposal_service
from app.budgets_db import GOAL_KINDS, Budget, Proposal, get_proposals_db
from app.database import get_db
from app.errors import log_and_raise
from app.models import Transaction
from app.routes.budgets import upsert_budget
from app.services.goals_service import (
    attribution_dicts,
    attributions_equal,
    attributions_for_transaction,
    delete_created_goal,
    get_goal,
    replace_txn_attributions,
    restore_goal_snapshot,
    set_goal_contribution,
    snapshot_goal,
    snapshots_equal,
    upsert_goal,
)
from app.services.tvm import money

router = APIRouter(prefix="/proposals", tags=["proposals"])

SUPPORTED_KINDS = {"set_budget", "set_goal", "update_goal_contribution", "attribute_transfer"}
GOAL_MUTATION_KINDS = {"set_goal", "update_goal_contribution"}
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


# ── Schemas ───────────────────────────────────────────────────────────────────

class SetBudgetPayload(BaseModel):
    payload_version: int = 1
    month: str = Field(..., description="YYYY-MM")
    category_name: str = Field(..., min_length=1)
    category_key: Optional[str] = Field(None, description="Plaid PFC parent, e.g. FOOD_AND_DRINK")
    limit: float = Field(..., gt=0)
    basis_limit: Optional[float] = Field(None, description="Current limit at propose time, for the before→after diff")
    color: Optional[str] = None


class SetGoalPayload(BaseModel):
    payload_version: int = 1
    goal_id: Optional[int] = None
    name: str = Field(..., min_length=1)
    kind: str = "custom"
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(0, ge=0)
    target_date: Optional[str] = None
    monthly_contribution: Optional[float] = Field(None, ge=0)
    annual_return_assumption: Optional[float] = Field(None, ge=0, le=0.12)
    basis: Optional[dict[str, Any]] = None
    color: Optional[str] = None


class UpdateGoalContributionPayload(BaseModel):
    payload_version: int = 1
    goal_id: int
    monthly_contribution: float = Field(..., gt=0)
    basis_contribution: Optional[float] = None
    goal_name: Optional[str] = None


class AttributionLine(BaseModel):
    goal_id: int
    amount: float = Field(..., gt=0)
    goal_name: Optional[str] = None


class AttributeTransferPayload(BaseModel):
    payload_version: int = 1
    transaction_id: int
    attributions: list[AttributionLine] = Field(..., min_length=1)
    basis_attributions: list[AttributionLine] = Field(default_factory=list)
    merchant: Optional[str] = None
    date: Optional[str] = None


class ProposalCreate(BaseModel):
    kind: str
    rationale: Optional[str] = None
    source: str = "claude"
    payload: dict[str, Any]


class ProposalOut(BaseModel):
    id: int
    kind: str
    status: str
    source: str
    rationale: Optional[str]
    payload: dict[str, Any]
    undo: Optional[dict[str, Any]]
    superseded_by: Optional[int]
    created_at: Optional[str]
    applied_at: Optional[str]
    summary: str
    category_name: Optional[str] = None
    basis_limit: Optional[float] = None
    proposed_limit: Optional[float] = None
    month: Optional[str] = None


class ProposalListResponse(BaseModel):
    proposals: list[ProposalOut]
    pending_count: int


class ApplyResponse(BaseModel):
    success: bool
    proposal_id: int
    kind: str
    entity_id: Optional[int] = None
    summary: str
    created: bool = False
    # Budget fields kept for the existing Advisor hook; optional for other kinds.
    budget_id: Optional[int] = None
    category_name: Optional[str] = None
    prev_limit: Optional[float] = None
    new_limit: Optional[float] = None


class MutateResponse(BaseModel):
    success: bool
    proposal_id: int
    status: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _set_budget_summary(payload: dict[str, Any]) -> str:
    name = payload.get("category_name", "?")
    limit = payload.get("limit")
    basis = payload.get("basis_limit")
    month = payload.get("month", "")
    if basis is not None and abs(float(basis) - float(limit)) > 1e-9:
        return f"{name} ${float(basis):,.0f} → ${float(limit):,.0f} ({month})"
    return f"Set {name} budget to ${float(limit):,.0f} ({month})"


def _set_goal_summary(payload: dict[str, Any]) -> str:
    name = payload.get("name", "Goal")
    target = payload.get("target_amount")
    pmt = payload.get("monthly_contribution")
    current = payload.get("current_amount") or 0
    parts = [name]
    if target is not None:
        parts.append(f"${float(current):,.0f} → ${float(target):,.0f}")
    if pmt is not None:
        parts.append(f"${float(pmt):,.0f}/mo")
    return " · ".join(parts)


def _contribution_summary(payload: dict[str, Any]) -> str:
    name = payload.get("goal_name") or "Goal"
    pmt = payload.get("monthly_contribution")
    basis = payload.get("basis_contribution")
    if basis is not None and pmt is not None:
        return f"{name} ${float(basis):,.0f}/mo → ${float(pmt):,.0f}/mo"
    if pmt is not None:
        return f"{name} ${float(pmt):,.0f}/mo"
    return name


def _label_summary(payload: dict[str, Any]) -> str:
    attrs = payload.get("attributions") or []
    merchant = payload.get("merchant") or "Transfer"
    if not attrs:
        return f"Label {merchant}"
    first = attrs[0]
    name = first.get("goal_name") or f"Goal {first.get('goal_id')}"
    amount = first.get("amount")
    extra = f" (+{len(attrs) - 1})" if len(attrs) > 1 else ""
    if amount is not None:
        return f"{merchant} ${float(amount):,.0f} → {name}{extra}"
    return f"{merchant} → {name}{extra}"


def _summary_for(kind: str, payload: dict[str, Any]) -> str:
    if kind == "set_budget":
        return _set_budget_summary(payload)
    if kind == "set_goal":
        return _set_goal_summary(payload)
    if kind == "update_goal_contribution":
        return _contribution_summary(payload)
    if kind == "attribute_transfer":
        return _label_summary(payload)
    return kind


def _to_out(p: Proposal) -> ProposalOut:
    payload = p.payload or {}
    return ProposalOut(
        id=p.id,
        kind=p.kind,
        status=p.status,
        source=p.source,
        rationale=p.rationale,
        payload=payload,
        undo=p.undo,
        superseded_by=p.superseded_by,
        created_at=_iso(p.created_at),
        applied_at=_iso(p.applied_at),
        summary=_summary_for(p.kind, payload),
        category_name=payload.get("category_name"),
        basis_limit=payload.get("basis_limit"),
        proposed_limit=payload.get("limit"),
        month=payload.get("month"),
    )


def _validate_set_budget(payload: dict[str, Any]) -> SetBudgetPayload:
    """Validate + normalize a set_budget payload, rejecting ambiguity up front."""
    try:
        model = SetBudgetPayload(**payload)
    except Exception as exc:  # pydantic ValidationError → 422 with a clear message
        raise HTTPException(status_code=422, detail=f"Invalid set_budget payload: {exc}")

    if not _MONTH_RE.match(model.month):
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    if model.category_key is not None and model.category_key not in KNOWN_CATEGORY_KEYS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown category_key '{model.category_key}'. Use a Plaid PFC parent "
                f"(e.g. FOOD_AND_DRINK) or omit it to match by display name."
            ),
        )

    # Normalize the display name: models sometimes pass the raw key as the name
    # ("FOOD_AND_DRINK"). If a key is present and the name is empty or looks like
    # a raw key, replace it with the human label so the applied budget reads well.
    name = (model.category_name or "").strip()
    if model.category_key and (not name or re.fullmatch(r"[A-Z][A-Z_]+", name)):
        model.category_name = display_label_for_key(model.category_key)
    else:
        model.category_name = name
    return model


def _validate_set_goal(payload: dict[str, Any]) -> SetGoalPayload:
    try:
        model = SetGoalPayload(**payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid set_goal payload: {exc}")
    if model.kind not in GOAL_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {GOAL_KINDS}")
    if model.target_date and not _DATE_RE.match(model.target_date):
        raise HTTPException(status_code=422, detail="target_date must be YYYY-MM-DD")
    model.name = model.name.strip()
    if not model.name:
        raise HTTPException(status_code=422, detail="name is required")
    return model


def _validate_goal_contribution(payload: dict[str, Any]) -> UpdateGoalContributionPayload:
    try:
        return UpdateGoalContributionPayload(**payload)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid update_goal_contribution payload: {exc}"
        )


def _validate_attribute_transfer(
    payload: dict[str, Any], ldb: Session | None = None
) -> AttributeTransferPayload:
    try:
        model = AttributeTransferPayload(**payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid attribute_transfer payload: {exc}")
    if ldb is not None:
        txn = (
            ldb.query(Transaction)
            .filter(Transaction.id == model.transaction_id, Transaction.removed.is_(False))
            .first()
        )
        if txn is None:
            raise HTTPException(status_code=422, detail="Transaction not found")
        if txn.hidden:
            raise HTTPException(status_code=422, detail="Transaction is hidden")
        if not model.merchant:
            model.merchant = txn.merchant
        if not model.date:
            model.date = txn.date.isoformat() if txn.date else None
    return model


def _validate_kind(kind: str, payload: dict[str, Any], ldb: Session | None = None) -> dict[str, Any]:
    if kind == "set_budget":
        return _validate_set_budget(payload).model_dump()
    if kind == "set_goal":
        return _validate_set_goal(payload).model_dump()
    if kind == "update_goal_contribution":
        return _validate_goal_contribution(payload).model_dump()
    if kind == "attribute_transfer":
        return _validate_attribute_transfer(payload, ldb).model_dump()
    raise HTTPException(status_code=422, detail=f"Unsupported kind '{kind}'")


def _same_budget_target(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if a.get("month") != b.get("month"):
        return False
    if a.get("category_key"):
        return a.get("category_key") == b.get("category_key")
    return a.get("category_name") == b.get("category_name")


def _pending_to_supersede(pdb: Session, kind: str, payload: dict[str, Any]) -> list[Proposal]:
    """Pending proposals that target the same entity as this new one."""
    candidates = (
        pdb.query(Proposal)
        .filter(Proposal.user_id == 1, Proposal.status == "pending")
        .all()
    )
    out: list[Proposal] = []
    for existing in candidates:
        ep = existing.payload or {}
        if kind == "set_budget":
            if existing.kind == "set_budget" and _same_budget_target(payload, ep):
                out.append(existing)
        elif kind in GOAL_MUTATION_KINDS:
            gid = payload.get("goal_id")
            if gid and existing.kind in GOAL_MUTATION_KINDS and ep.get("goal_id") == gid:
                out.append(existing)
            elif (
                kind == "set_goal"
                and not gid
                and existing.kind == "set_goal"
                and not ep.get("goal_id")
                and ep.get("name") == payload.get("name")
                and ep.get("kind") == payload.get("kind")
            ):
                out.append(existing)
        elif kind == "attribute_transfer":
            if (
                existing.kind == "attribute_transfer"
                and ep.get("transaction_id") == payload.get("transaction_id")
            ):
                out.append(existing)
    return out


# ── Create (MCP service key only) ─────────────────────────────────────────────

@router.post("", response_model=ProposalOut, dependencies=[Depends(require_proposal_service)])
async def create_proposal(
    req: ProposalCreate,
    pdb: Session = Depends(get_proposals_db),
    ldb: Session = Depends(get_db),
):
    """Stage a new proposal. Called by the MCP server's propose_* tools.

    Deduplicates: if a pending proposal already targets the same entity, the old
    one is superseded so the Advisor queue never fills with duplicates from a
    single conversation.
    """
    if req.kind not in SUPPORTED_KINDS:
        raise HTTPException(status_code=422, detail=f"Unsupported kind '{req.kind}'")

    try:
        normalized = _validate_kind(req.kind, req.payload, ldb)
        priors = _pending_to_supersede(pdb, req.kind, normalized)

        proposal = Proposal(
            user_id=1,
            kind=req.kind,
            status="pending",
            source=req.source or "claude",
            payload=normalized,
            rationale=req.rationale,
        )
        pdb.add(proposal)
        pdb.flush()

        for prior in priors:
            prior.status = "superseded"
            prior.superseded_by = proposal.id

        pdb.commit()
        pdb.refresh(proposal)
        return _to_out(proposal)
    except HTTPException:
        pdb.rollback()
        raise
    except Exception as e:
        pdb.rollback()
        log_and_raise(e)


# ── List (user session) ───────────────────────────────────────────────────────

@router.get("", response_model=ProposalListResponse, dependencies=[Depends(require_auth)])
async def list_proposals(
    status: Optional[str] = Query("pending", description="Filter by status; 'all' for everything"),
    pdb: Session = Depends(get_proposals_db),
):
    query = pdb.query(Proposal).filter(Proposal.user_id == 1)
    if status and status != "all":
        query = query.filter(Proposal.status == status)
    rows = query.order_by(Proposal.created_at.desc()).all()

    pending_count = (
        pdb.query(Proposal)
        .filter(Proposal.user_id == 1, Proposal.status == "pending")
        .count()
    )
    return ProposalListResponse(
        proposals=[_to_out(p) for p in rows],
        pending_count=pending_count,
    )


# ── Apply (user session) — THE ONLY MUTATION PATH ─────────────────────────────

@router.post("/{proposal_id}/apply", response_model=ApplyResponse, dependencies=[Depends(require_auth)])
async def apply_proposal(
    proposal_id: int,
    pdb: Session = Depends(get_proposals_db),
    ldb: Session = Depends(get_db),
):
    """Apply a pending proposal. Re-validates against current data and writes via
    the shared in-process writers used by the Goals / Budgets REST APIs."""
    proposal = pdb.query(Proposal).filter(Proposal.id == proposal_id, Proposal.user_id == 1).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is '{proposal.status}', not pending")
    if proposal.kind not in SUPPORTED_KINDS:
        raise HTTPException(status_code=422, detail=f"Cannot apply kind '{proposal.kind}'")

    try:
        if proposal.kind == "set_budget":
            return _apply_set_budget(proposal, pdb)
        if proposal.kind == "set_goal":
            return _apply_set_goal(proposal, pdb)
        if proposal.kind == "update_goal_contribution":
            return _apply_goal_contribution(proposal, pdb)
        return _apply_attribute_transfer(proposal, pdb, ldb)
    except HTTPException:
        pdb.rollback()
        ldb.rollback()
        raise
    except ValueError as e:
        pdb.rollback()
        ldb.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        pdb.rollback()
        ldb.rollback()
        log_and_raise(e)


def _apply_set_budget(proposal: Proposal, pdb: Session) -> ApplyResponse:
    model = _validate_set_budget(proposal.payload or {})
    budget, prev_limit, existed = upsert_budget(
        pdb,
        month=model.month,
        category_name=model.category_name,
        category_key=model.category_key,
        limit=model.limit,
        color=model.color,
    )
    proposal.status = "applied"
    proposal.applied_at = datetime.utcnow()
    proposal.undo = {
        "budget_id": budget.id,
        "prev_limit": prev_limit,
        "budget_existed": existed,
        "applied_limit": float(model.limit),
    }
    pdb.commit()
    return ApplyResponse(
        success=True,
        proposal_id=proposal.id,
        kind=proposal.kind,
        entity_id=budget.id,
        summary=_set_budget_summary(proposal.payload or {}),
        created=not existed,
        budget_id=budget.id,
        category_name=budget.category_name,
        prev_limit=prev_limit,
        new_limit=float(model.limit),
    )


def _apply_set_goal(proposal: Proposal, pdb: Session) -> ApplyResponse:
    model = _validate_set_goal(proposal.payload or {})
    if model.goal_id is not None:
        existing = get_goal(pdb, model.goal_id)
        if existing.status not in ("active", "paused"):
            raise HTTPException(status_code=422, detail="Goal is not active or paused")
    status = existing.status if model.goal_id is not None else "active"
    goal, prev, created = upsert_goal(
        pdb,
        goal_id=model.goal_id,
        name=model.name,
        kind=model.kind,
        target_amount=model.target_amount,
        current_amount=model.current_amount,
        target_date=model.target_date,
        monthly_contribution=model.monthly_contribution,
        annual_return_assumption=model.annual_return_assumption,
        status=status,
        color=model.color,
    )
    applied = snapshot_goal(goal)
    proposal.status = "applied"
    proposal.applied_at = datetime.utcnow()
    proposal.undo = {
        "created": created,
        "goal_id": goal.id,
        "prev": prev,
        "applied": applied,
    }
    pdb.commit()
    return ApplyResponse(
        success=True,
        proposal_id=proposal.id,
        kind=proposal.kind,
        entity_id=goal.id,
        summary=_set_goal_summary(proposal.payload or {}),
        created=created,
    )


def _apply_goal_contribution(proposal: Proposal, pdb: Session) -> ApplyResponse:
    model = _validate_goal_contribution(proposal.payload or {})
    goal = get_goal(pdb, model.goal_id)
    if goal.status not in ("active", "paused"):
        raise HTTPException(status_code=422, detail="Goal is not active or paused")
    goal, prev = set_goal_contribution(pdb, model.goal_id, model.monthly_contribution)
    proposal.status = "applied"
    proposal.applied_at = datetime.utcnow()
    proposal.undo = {
        "goal_id": goal.id,
        "prev_contribution": prev,
        "applied_contribution": float(model.monthly_contribution),
    }
    pdb.commit()
    return ApplyResponse(
        success=True,
        proposal_id=proposal.id,
        kind=proposal.kind,
        entity_id=goal.id,
        summary=_contribution_summary(proposal.payload or {}),
        created=False,
    )


def _apply_attribute_transfer(proposal: Proposal, pdb: Session, ldb: Session) -> ApplyResponse:
    model = _validate_attribute_transfer(proposal.payload or {}, ldb)
    items = [(row.goal_id, row.amount) for row in model.attributions]
    prior = replace_txn_attributions(ldb, pdb, model.transaction_id, items)
    applied = [{"goal_id": gid, "amount": money(amt)} for gid, amt in items]
    proposal.status = "applied"
    proposal.applied_at = datetime.utcnow()
    proposal.undo = {
        "transaction_id": model.transaction_id,
        "prev": prior,
        "applied": applied,
    }
    ldb.commit()
    pdb.commit()
    return ApplyResponse(
        success=True,
        proposal_id=proposal.id,
        kind=proposal.kind,
        entity_id=model.transaction_id,
        summary=_label_summary(proposal.payload or {}),
        created=False,
    )


# ── Dismiss (user session) ────────────────────────────────────────────────────

@router.post("/{proposal_id}/dismiss", response_model=MutateResponse, dependencies=[Depends(require_auth)])
async def dismiss_proposal(proposal_id: int, pdb: Session = Depends(get_proposals_db)):
    proposal = pdb.query(Proposal).filter(Proposal.id == proposal_id, Proposal.user_id == 1).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is '{proposal.status}', not pending")
    try:
        proposal.status = "dismissed"
        proposal.dismissed_at = datetime.utcnow()
        pdb.commit()
        return MutateResponse(success=True, proposal_id=proposal.id, status="dismissed")
    except Exception as e:
        pdb.rollback()
        log_and_raise(e)


# ── Undo (user session) ───────────────────────────────────────────────────────

@router.post("/{proposal_id}/undo", response_model=MutateResponse, dependencies=[Depends(require_auth)])
async def undo_proposal(
    proposal_id: int,
    pdb: Session = Depends(get_proposals_db),
    ldb: Session = Depends(get_db),
):
    """Revert an applied proposal. Optimistic concurrency: refuse (409) if the
    user changed the goal, budget, or labels in the UI after Apply."""
    proposal = pdb.query(Proposal).filter(Proposal.id == proposal_id, Proposal.user_id == 1).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "applied":
        raise HTTPException(status_code=409, detail=f"Only applied proposals can be undone (is '{proposal.status}')")

    try:
        if proposal.kind == "set_budget":
            _undo_set_budget(proposal, pdb)
        elif proposal.kind == "set_goal":
            _undo_set_goal(proposal, pdb)
        elif proposal.kind == "update_goal_contribution":
            _undo_goal_contribution(proposal, pdb)
        elif proposal.kind == "attribute_transfer":
            _undo_attribute_transfer(proposal, pdb, ldb)
        else:
            raise HTTPException(status_code=422, detail=f"Cannot undo kind '{proposal.kind}'")
        proposal.status = "undone"
        proposal.undone_at = datetime.utcnow()
        pdb.commit()
        return MutateResponse(success=True, proposal_id=proposal.id, status="undone")
    except HTTPException:
        pdb.rollback()
        ldb.rollback()
        raise
    except ValueError as e:
        pdb.rollback()
        ldb.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        pdb.rollback()
        ldb.rollback()
        log_and_raise(e)


def _undo_set_budget(proposal: Proposal, pdb: Session) -> None:
    undo = proposal.undo or {}
    budget_id = undo.get("budget_id")
    budget = pdb.query(Budget).filter(Budget.id == budget_id, Budget.user_id == 1).first() if budget_id else None

    applied_limit = undo.get("applied_limit")
    if budget is not None and applied_limit is not None and abs(float(budget.limit) - float(applied_limit)) > 1e-9:
        raise HTTPException(
            status_code=409,
            detail="Budget changed since this was applied; undo refused to avoid overwriting your edit.",
        )
    if budget is not None:
        if undo.get("budget_existed"):
            budget.limit = undo.get("prev_limit")
        else:
            pdb.delete(budget)


def _undo_set_goal(proposal: Proposal, pdb: Session) -> None:
    undo = proposal.undo or {}
    goal_id = undo.get("goal_id")
    applied = undo.get("applied") or {}
    try:
        goal = get_goal(pdb, int(goal_id))
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail="Goal is missing; undo refused.",
        ) from e
    if not snapshots_equal(snapshot_goal(goal), applied):
        raise HTTPException(
            status_code=409,
            detail="Goal changed since this was applied; undo refused to avoid overwriting your edit.",
        )
    if undo.get("created"):
        delete_created_goal(pdb, int(goal_id))
    else:
        prev = undo.get("prev")
        if not prev:
            raise HTTPException(status_code=409, detail="No prior goal snapshot to restore.")
        restore_goal_snapshot(pdb, prev)


def _undo_goal_contribution(proposal: Proposal, pdb: Session) -> None:
    undo = proposal.undo or {}
    goal_id = undo.get("goal_id")
    applied = undo.get("applied_contribution")
    try:
        goal = get_goal(pdb, int(goal_id))
    except ValueError as e:
        raise HTTPException(status_code=409, detail="Goal is missing; undo refused.") from e
    current = float(goal.monthly_contribution) if goal.monthly_contribution is not None else None
    if applied is not None and current is not None and abs(current - float(applied)) > 1e-9:
        raise HTTPException(
            status_code=409,
            detail="Contribution changed since this was applied; undo refused to avoid overwriting your edit.",
        )
    if applied is not None and current is None:
        raise HTTPException(
            status_code=409,
            detail="Contribution changed since this was applied; undo refused to avoid overwriting your edit.",
        )
    prev = undo.get("prev_contribution")
    goal.monthly_contribution = prev


def _undo_attribute_transfer(proposal: Proposal, pdb: Session, ldb: Session) -> None:
    undo = proposal.undo or {}
    txn_id = undo.get("transaction_id")
    applied = undo.get("applied") or []
    current = attribution_dicts(attributions_for_transaction(ldb, int(txn_id)))
    if not attributions_equal(current, applied):
        raise HTTPException(
            status_code=409,
            detail="Labels changed since this was applied; undo refused to avoid overwriting your edit.",
        )
    prev = undo.get("prev") or []
    items = [(int(row["goal_id"]), float(row["amount"])) for row in prev]
    replace_txn_attributions(ldb, pdb, int(txn_id), items)
    ldb.commit()
