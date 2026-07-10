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

from app.budgets_db import Budget
from mcp_server.db import budgets_session
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
        month=month,
        category_name=category_name,
        category_key=category_key,
        basis_limit=basis_limit,
        proposed_limit=round(float(limit), 2),
        apply_url=apply_url,
        message=(
            f"Staged proposal #{pid}: {data.get('summary')}. "
            f"The user reviews and applies it in Ledger — open {apply_url}. "
            "You cannot apply it yourself."
        ),
    )


def _safe_detail(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("detail", resp.text))
    except Exception:
        return resp.text
