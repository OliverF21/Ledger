"""
Write-intent bridge for the MCP server.

The propose_* tools do NOT touch any database. They read the current budget
(read-only) to compute a before→after basis, then HTTP POST a staged proposal
to the running Ledger backend, which the user later applies in the Advisor page.

This requires the FastAPI backend to be running (unlike the read tools, which
query the SQLite files directly). We health-check first and return a clear
message if it is down.
"""

from __future__ import annotations

import os
from datetime import date

import requests

from app.budgets_db import Budget, FinancialGoal
from app.models import Transaction
from app.txn_classifier import classify_orm_transaction
from mcp_server.db import budgets_session, ledger_session
from mcp_server.schemas import ProposalResult

# Where the backend API lives (for the POST) and where the user's browser reaches
# the app (for the clickable apply link). Same host by default; override
# LEDGER_APP_URL with your Tailscale MagicDNS URL (e.g. http://ledger:8000).
LEDGER_API_URL = os.getenv("LEDGER_API_URL", "http://127.0.0.1:8000").rstrip("/")
LEDGER_APP_URL = os.getenv("LEDGER_APP_URL", LEDGER_API_URL).rstrip("/")
PROPOSAL_SERVICE_KEY = os.getenv("PROPOSAL_SERVICE_KEY", "")

_HTTP_TIMEOUT = 8


def _current_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _backend_down_result(detail: str) -> ProposalResult:
    return ProposalResult(
        ok=False,
        message=(
            f"Could not reach the Ledger backend at {LEDGER_API_URL} ({detail}). "
            "Start it first (the 'Ledger' service, or `uvicorn main:app` from backend/) "
            "and try again."
        ),
    )


def _backend_healthy() -> tuple[bool, str]:
    try:
        r = requests.get(f"{LEDGER_API_URL}/health", timeout=_HTTP_TIMEOUT)
        return (r.ok, f"HTTP {r.status_code}")
    except requests.RequestException as exc:
        return (False, str(exc))


def _lookup_basis_limit(month: str, category_name: str, category_key: str | None) -> float | None:
    """Read the current budget limit (if any) so the proposal can show a diff."""
    with budgets_session() as bdb:
        query = bdb.query(Budget).filter(Budget.user_id == 1, Budget.month == month)
        if category_key:
            existing = query.filter(Budget.category_key == category_key).first()
        else:
            existing = query.filter(Budget.category_name == category_name).first()
        return float(existing.limit) if existing else None


def create_budget_proposal(
    *,
    category_name: str,
    limit: float,
    month: str | None = None,
    category_key: str | None = None,
    rationale: str | None = None,
) -> ProposalResult:
    """Stage a set_budget proposal in Ledger for the user to review and apply."""
    if not PROPOSAL_SERVICE_KEY:
        return ProposalResult(
            ok=False,
            message=(
                "PROPOSAL_SERVICE_KEY is not set in the MCP server environment, so "
                "proposals cannot be created. Set it (matching the backend's value) "
                "in backend/.env."
            ),
        )
    if limit <= 0:
        return ProposalResult(ok=False, message="limit must be greater than 0.")

    month = month or _current_month()

    healthy, detail = _backend_healthy()
    if not healthy:
        return _backend_down_result(detail)

    basis_limit = _lookup_basis_limit(month, category_name, category_key)

    payload = {
        "payload_version": 1,
        "month": month,
        "category_name": category_name,
        "category_key": category_key,
        "limit": round(float(limit), 2),
        "basis_limit": basis_limit,
    }
    body = {"kind": "set_budget", "rationale": rationale, "source": "claude", "payload": payload}

    try:
        resp = requests.post(
            f"{LEDGER_API_URL}/api/proposals",
            json=body,
            headers={"X-Proposal-Key": PROPOSAL_SERVICE_KEY},
            timeout=_HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        return _backend_down_result(str(exc))

    if resp.status_code == 401:
        return ProposalResult(ok=False, message="Ledger rejected the proposal key (401). Check PROPOSAL_SERVICE_KEY matches the backend.")
    if resp.status_code == 503:
        return ProposalResult(ok=False, message="Ledger has no PROPOSAL_SERVICE_KEY configured (503); set it in backend/.env and restart.")
    if resp.status_code == 422:
        detail = _safe_detail(resp)
        return ProposalResult(ok=False, message=f"Ledger rejected the proposal: {detail}")
    if not resp.ok:
        return ProposalResult(ok=False, message=f"Ledger returned HTTP {resp.status_code}: {_safe_detail(resp)}")

    data = resp.json()
    pid = data.get("id")
    apply_url = f"{LEDGER_APP_URL}/?proposal={pid}#advisor"
    return ProposalResult(
        ok=True,
        proposal_id=pid,
        status=data.get("status"),
        summary=data.get("summary"),
        kind="set_budget",
        month=month,
        category_name=category_name,
        category_key=category_key,
        basis_limit=basis_limit,
        proposed_limit=round(float(limit), 2),
        apply_url=apply_url,
        message=(
            f"Staged proposal #{pid}: {data.get('summary')}. "
            f"The user reviews and applies it in Ledger. Open {apply_url}. "
            "You cannot apply it yourself."
        ),
    )


def _post_proposal(kind: str, payload: dict, rationale: str | None) -> ProposalResult:
    if not PROPOSAL_SERVICE_KEY:
        return ProposalResult(
            ok=False,
            message=(
                "PROPOSAL_SERVICE_KEY is not set in the MCP server environment, so "
                "proposals cannot be created. Set it (matching the backend's value) "
                "in backend/.env."
            ),
        )
    healthy, detail = _backend_healthy()
    if not healthy:
        return _backend_down_result(detail)

    body = {"kind": kind, "rationale": rationale, "source": "claude", "payload": payload}
    try:
        resp = requests.post(
            f"{LEDGER_API_URL}/api/proposals",
            json=body,
            headers={"X-Proposal-Key": PROPOSAL_SERVICE_KEY},
            timeout=_HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        return _backend_down_result(str(exc))

    if resp.status_code == 401:
        return ProposalResult(
            ok=False,
            message="Ledger rejected the proposal key (401). Check PROPOSAL_SERVICE_KEY matches the backend.",
        )
    if resp.status_code == 503:
        return ProposalResult(
            ok=False,
            message="Ledger has no PROPOSAL_SERVICE_KEY configured (503); set it in backend/.env and restart.",
        )
    if resp.status_code == 422:
        return ProposalResult(ok=False, message=f"Ledger rejected the proposal: {_safe_detail(resp)}")
    if not resp.ok:
        return ProposalResult(ok=False, message=f"Ledger returned HTTP {resp.status_code}: {_safe_detail(resp)}")

    data = resp.json()
    pid = data.get("id")
    apply_url = f"{LEDGER_APP_URL}/?proposal={pid}#advisor"
    return ProposalResult(
        ok=True,
        proposal_id=pid,
        status=data.get("status"),
        summary=data.get("summary"),
        kind=kind,
        goal_id=payload.get("goal_id"),
        goal_name=payload.get("name") or payload.get("goal_name"),
        transaction_id=payload.get("transaction_id"),
        apply_url=apply_url,
        message=(
            f"Staged proposal #{pid}: {data.get('summary')}. "
            f"The user reviews and applies it in Ledger — open {apply_url}. "
            "You cannot apply it yourself. Do not claim the change is live."
        ),
    )


def create_goal_proposal(
    *,
    name: str,
    target_amount: float,
    kind: str = "custom",
    goal_id: int | None = None,
    current_amount: float = 0.0,
    target_date: str | None = None,
    monthly_contribution: float | None = None,
    annual_return_assumption: float | None = None,
    rationale: str | None = None,
) -> ProposalResult:
    """Stage a set_goal proposal. Does not write FinancialGoal until the user Applies."""
    if target_amount <= 0:
        return ProposalResult(ok=False, message="target_amount must be greater than 0.")
    if annual_return_assumption is not None and (
        annual_return_assumption < 0 or annual_return_assumption > 0.12
    ):
        return ProposalResult(ok=False, message="annual_return_assumption must be between 0 and 0.12.")

    payload = {
        "payload_version": 1,
        "goal_id": goal_id,
        "name": name.strip(),
        "kind": kind,
        "target_amount": round(float(target_amount), 2),
        "current_amount": round(float(current_amount or 0), 2),
        "target_date": target_date,
        "monthly_contribution": (
            round(float(monthly_contribution), 2) if monthly_contribution is not None else None
        ),
        "annual_return_assumption": annual_return_assumption,
        "basis": None,
    }
    if goal_id is not None:
        with budgets_session() as bdb:
            goal = (
                bdb.query(FinancialGoal)
                .filter(FinancialGoal.id == goal_id, FinancialGoal.user_id == 1)
                .first()
            )
            if goal is not None:
                payload["basis"] = {
                    "name": goal.name,
                    "kind": goal.kind,
                    "target_amount": float(goal.target_amount),
                    "current_amount": float(goal.current_amount or 0),
                    "monthly_contribution": (
                        float(goal.monthly_contribution) if goal.monthly_contribution is not None else None
                    ),
                    "annual_return_assumption": (
                        float(goal.annual_return_assumption)
                        if goal.annual_return_assumption is not None
                        else None
                    ),
                    "status": goal.status,
                }
    return _post_proposal("set_goal", payload, rationale)


def create_goal_contribution_proposal(
    *,
    goal_id: int,
    monthly_contribution: float,
    rationale: str | None = None,
) -> ProposalResult:
    if monthly_contribution <= 0:
        return ProposalResult(ok=False, message="monthly_contribution must be greater than 0.")
    goal_name = None
    basis = None
    with budgets_session() as bdb:
        goal = (
            bdb.query(FinancialGoal)
            .filter(FinancialGoal.id == goal_id, FinancialGoal.user_id == 1)
            .first()
        )
        if goal is None:
            return ProposalResult(ok=False, message=f"Goal {goal_id} not found.")
        goal_name = goal.name
        basis = float(goal.monthly_contribution) if goal.monthly_contribution is not None else None
    payload = {
        "payload_version": 1,
        "goal_id": goal_id,
        "monthly_contribution": round(float(monthly_contribution), 2),
        "basis_contribution": basis,
        "goal_name": goal_name,
    }
    return _post_proposal("update_goal_contribution", payload, rationale)


def create_transfer_label_proposal(
    *,
    transaction_id: int,
    attributions: list[dict],
    rationale: str | None = None,
) -> ProposalResult:
    if not attributions:
        return ProposalResult(ok=False, message="attributions must include at least one goal label.")

    merchant = None
    txn_date = None
    role_note = None
    with ledger_session() as ldb:
        txn = (
            ldb.query(Transaction)
            .filter(Transaction.id == transaction_id, Transaction.removed.is_(False))
            .first()
        )
        if txn is None:
            return ProposalResult(ok=False, message=f"Transaction {transaction_id} not found.")
        merchant = txn.merchant
        txn_date = txn.date.isoformat() if txn.date else None
        role = classify_orm_transaction(txn)
        if role == "spending":
            role_note = (
                "This row looks like spending, not a savings/investment transfer. "
                "Labeling it still works, but mention that in the Advisor rationale."
            )

    named: list[dict] = []
    basis: list[dict] = []
    with budgets_session() as bdb:
        goals = {
            g.id: g
            for g in bdb.query(FinancialGoal).filter(FinancialGoal.user_id == 1).all()
        }
        for row in attributions:
            gid = int(row["goal_id"])
            goal = goals.get(gid)
            named.append(
                {
                    "goal_id": gid,
                    "amount": round(float(row["amount"]), 2),
                    "goal_name": goal.name if goal is not None else f"Goal {gid}",
                }
            )
        with ledger_session() as ldb:
            from app.services.goals_service import attributions_for_transaction

            for attr in attributions_for_transaction(ldb, transaction_id):
                goal = goals.get(attr.goal_id)
                basis.append(
                    {
                        "goal_id": attr.goal_id,
                        "amount": round(float(attr.amount), 2),
                        "goal_name": goal.name if goal is not None else f"Goal {attr.goal_id}",
                    }
                )

    rationale_out = rationale or ""
    if role_note:
        rationale_out = f"{rationale_out} {role_note}".strip() if rationale_out else role_note

    payload = {
        "payload_version": 1,
        "transaction_id": transaction_id,
        "attributions": named,
        "basis_attributions": basis,
        "merchant": merchant,
        "date": txn_date,
    }
    result = _post_proposal("attribute_transfer", payload, rationale_out or None)
    if result.ok:
        result.transaction_id = transaction_id
        result.goal_name = named[0].get("goal_name")
    return result


def _safe_detail(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("detail", resp.text))
    except Exception:
        return resp.text
