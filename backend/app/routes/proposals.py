"""
AI advisor proposal endpoints.

A proposal is an AI-generated *intent* (created by the MCP server's propose_*
tools) staged in the `proposals` table of budgets.db. It has NO effect on real
data until the user applies it in the Advisor page.

Auth split (deliberate — this is the trust boundary):
- POST /proposals              → require_proposal_service (MCP create-only key)
- GET  /proposals              → require_auth (user session)
- POST /proposals/{id}/apply   → require_auth  ← the ONLY route that mutates a budget
- POST /proposals/{id}/dismiss → require_auth
- POST /proposals/{id}/undo    → require_auth

The MCP server can only ever CREATE pending proposals. Applying, dismissing, and
undoing require the user's browser session — Claude cannot do them.

Only kind="set_budget" is implemented. Apply is an upsert (create-or-update),
because the common advice is changing an *existing* budget, not creating one.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analytics_shared import KNOWN_CATEGORY_KEYS, display_label_for_key
from app.auth import require_auth, require_proposal_service
from app.budgets_db import Budget, Proposal, get_proposals_db
from app.database import get_db
from app.errors import log_and_raise
from app.routes.budgets import upsert_budget

router = APIRouter(prefix="/proposals", tags=["proposals"])

SUPPORTED_KINDS = {"set_budget"}
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ── Schemas ───────────────────────────────────────────────────────────────────

class SetBudgetPayload(BaseModel):
    payload_version: int = 1
    month: str = Field(..., description="YYYY-MM")
    category_name: str = Field(..., min_length=1)
    category_key: Optional[str] = Field(None, description="Plaid PFC parent, e.g. FOOD_AND_DRINK")
    limit: float = Field(..., gt=0)
    basis_limit: Optional[float] = Field(None, description="Current limit at propose time, for the before→after diff")
    color: Optional[str] = None


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
    # Convenience fields for the UI (derived from payload for set_budget).
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
    budget_id: int
    category_name: str
    prev_limit: Optional[float]
    new_limit: float
    created: bool  # True if a new budget was created, False if updated


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
        summary=_set_budget_summary(payload) if p.kind == "set_budget" else p.kind,
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


def _pending_match(pdb: Session, kind: str, payload: SetBudgetPayload) -> Optional[Proposal]:
    """Find an existing pending proposal for the same target (for supersede)."""
    candidates = (
        pdb.query(Proposal)
        .filter(Proposal.user_id == 1, Proposal.kind == kind, Proposal.status == "pending")
        .all()
    )
    for c in candidates:
        cp = c.payload or {}
        if cp.get("month") != payload.month:
            continue
        if payload.category_key:
            if cp.get("category_key") == payload.category_key:
                return c
        elif cp.get("category_name") == payload.category_name:
            return c
    return None


# ── Create (MCP service key only) ─────────────────────────────────────────────

@router.post("", response_model=ProposalOut, dependencies=[Depends(require_proposal_service)])
async def create_proposal(req: ProposalCreate, pdb: Session = Depends(get_proposals_db)):
    """Stage a new proposal. Called by the MCP server's propose_* tools.

    Deduplicates: if a pending proposal already targets the same budget, the old
    one is superseded so the Advisor queue never fills with duplicates from a
    single conversation.
    """
    if req.kind not in SUPPORTED_KINDS:
        raise HTTPException(status_code=422, detail=f"Unsupported kind '{req.kind}'")

    try:
        model = _validate_set_budget(req.payload)
        normalized = model.model_dump()

        prior = _pending_match(pdb, req.kind, model)

        proposal = Proposal(
            user_id=1,
            kind=req.kind,
            status="pending",
            source=req.source or "claude",
            payload=normalized,
            rationale=req.rationale,
        )
        pdb.add(proposal)
        pdb.flush()  # assign proposal.id before wiring supersede pointer

        if prior is not None:
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
    ldb: Session = Depends(get_db),  # unused now, reserved for kinds that read ledger.db
):
    """Apply a pending proposal. Re-validates against current data, writes the
    budget via the shared in-process writer, and records undo state."""
    proposal = pdb.query(Proposal).filter(Proposal.id == proposal_id, Proposal.user_id == 1).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        # Idempotent: re-applying a resolved proposal is a conflict, not a silent no-op.
        raise HTTPException(status_code=409, detail=f"Proposal is '{proposal.status}', not pending")
    if proposal.kind != "set_budget":
        raise HTTPException(status_code=422, detail=f"Cannot apply kind '{proposal.kind}'")

    # Re-validate the payload against current rules (month/limit/category_key).
    model = _validate_set_budget(proposal.payload or {})

    try:
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
            budget_id=budget.id,
            category_name=budget.category_name,
            prev_limit=prev_limit,
            new_limit=float(model.limit),
            created=not existed,
        )
    except HTTPException:
        pdb.rollback()
        raise
    except Exception as e:
        pdb.rollback()
        log_and_raise(e)


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
async def undo_proposal(proposal_id: int, pdb: Session = Depends(get_proposals_db)):
    """Revert an applied proposal. Optimistic concurrency: only reverts if the
    budget still holds the value we applied — if the user changed it since, we
    refuse rather than surprise them."""
    proposal = pdb.query(Proposal).filter(Proposal.id == proposal_id, Proposal.user_id == 1).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "applied":
        raise HTTPException(status_code=409, detail=f"Only applied proposals can be undone (is '{proposal.status}')")

    undo = proposal.undo or {}
    budget_id = undo.get("budget_id")
    budget = pdb.query(Budget).filter(Budget.id == budget_id, Budget.user_id == 1).first() if budget_id else None

    applied_limit = undo.get("applied_limit")
    if budget is not None and applied_limit is not None and abs(float(budget.limit) - float(applied_limit)) > 1e-9:
        raise HTTPException(
            status_code=409,
            detail="Budget changed since this was applied; undo refused to avoid overwriting your edit.",
        )

    try:
        if budget is not None:
            if undo.get("budget_existed"):
                budget.limit = undo.get("prev_limit")  # restore prior limit
            else:
                pdb.delete(budget)  # we created it — remove it
        proposal.status = "undone"
        proposal.undone_at = datetime.utcnow()
        pdb.commit()
        return MutateResponse(success=True, proposal_id=proposal.id, status="undone")
    except Exception as e:
        pdb.rollback()
        log_and_raise(e)
