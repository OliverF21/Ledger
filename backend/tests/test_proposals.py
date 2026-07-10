"""
Integration tests for the AI advisor proposal loop.

Covers the invariant that matters most: a proposal only mutates budgets.db via
POST /api/proposals/{id}/apply, apply is an UPSERT (handles the common "change
an existing budget" case), and the auth split holds (create = service key,
apply/dismiss/undo = user session).

Env must be set before importing app modules (security.py raises at import if
ENCRYPTION_KEY is missing).
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PLAID_CLIENT_ID", "test_client_id")
os.environ.setdefault("PLAID_SANDBOX_SECRET", "test_sandbox_secret")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, database  # noqa: E402
from app.budgets_db import Budget, BudgetsBase, Proposal, get_budgets_db  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Base  # noqa: E402

PROPOSAL_KEY = "test-proposal-key"


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    """A TestClient with proposals/budgets and ledger pointed at throwaway DBs,
    via dependency overrides (no lifespan, no real DB files touched)."""
    # require_proposal_service resolves the effective key via
    # app.auth._proposal_service_key() (app_config table, then os.getenv) —
    # mirrors PlaidService._setting. Use setenv (not monkeypatch.setattr on
    # the frozen auth.PROPOSAL_SERVICE_KEY constant, which that resolver no
    # longer reads) so it takes effect, and clear it first in case a real
    # backend/.env has one set (see tests/test_plaid_config_api.py's note on
    # load_dotenv leaking into the test env).
    monkeypatch.setenv("PROPOSAL_SERVICE_KEY", PROPOSAL_KEY)

    budgets_engine = create_engine(f"sqlite:///{tmp_path / 'budgets.db'}", connect_args={"check_same_thread": False})
    ledger_engine = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False})
    BudgetsBase.metadata.create_all(budgets_engine)
    Base.metadata.create_all(ledger_engine)

    BudgetsSession = sessionmaker(bind=budgets_engine, autoflush=False, autocommit=False)
    LedgerSession = sessionmaker(bind=ledger_engine, autoflush=False, autocommit=False)

    # _proposal_service_key() also checks app_config first via its own
    # SessionLocal() — point that at the same throwaway ledger DB so it
    # doesn't read a real backend/ledger.db's app_config table.
    monkeypatch.setattr(database, "SessionLocal", LedgerSession)

    import main  # imported here so ENCRYPTION_KEY is already set
    app = main.app

    def _budgets_dep():
        db = BudgetsSession()
        try:
            yield db
        finally:
            db.close()

    def _ledger_dep():
        db = LedgerSession()
        try:
            yield db
        finally:
            db.close()

    # get_proposals_db is an alias of get_budgets_db, so this override covers both.
    app.dependency_overrides[get_budgets_db] = _budgets_dep
    app.dependency_overrides[get_db] = _ledger_dep

    token = auth.create_session_token(1)
    client = TestClient(app)  # no context manager → lifespan skipped

    class Ctx:
        pass

    c = Ctx()
    c.client = client
    c.token = token
    c.session = BudgetsSession
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


def _auth_headers(ctx):
    return {"Authorization": f"Bearer {ctx.token}"}


def _svc_headers():
    return {"X-Proposal-Key": PROPOSAL_KEY}


def _make_payload(**over):
    payload = {
        "payload_version": 1,
        "month": "2026-07",
        "category_name": "Food & Drink",
        "category_key": "FOOD_AND_DRINK",
        "limit": 400.0,
        "basis_limit": None,
    }
    payload.update(over)
    return {"kind": "set_budget", "rationale": "You spent $550 last month.", "payload": payload}


# ── Auth boundary ─────────────────────────────────────────────────────────────

def test_create_requires_service_key(ctx):
    # No key → 401
    r = ctx.client.post("/api/proposals", json=_make_payload())
    assert r.status_code == 401
    # User session is NOT accepted for create
    r2 = ctx.client.post("/api/proposals", json=_make_payload(), headers=_auth_headers(ctx))
    assert r2.status_code == 401


def test_list_and_apply_require_user_session(ctx):
    assert ctx.client.get("/api/proposals").status_code == 401
    # Service key must NOT grant apply/list
    assert ctx.client.get("/api/proposals", headers=_svc_headers()).status_code == 401


# ── Round trip: create → list → apply → budgets.db ────────────────────────────

def test_round_trip_creates_budget(ctx):
    r = ctx.client.post("/api/proposals", json=_make_payload(), headers=_svc_headers())
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert r.json()["status"] == "pending"

    lst = ctx.client.get("/api/proposals", headers=_auth_headers(ctx)).json()
    assert lst["pending_count"] == 1
    assert lst["proposals"][0]["id"] == pid

    ap = ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx))
    assert ap.status_code == 200, ap.text
    body = ap.json()
    assert body["created"] is True
    assert body["new_limit"] == 400.0

    # Assert the budget actually landed in budgets.db
    s = ctx.session()
    try:
        b = s.query(Budget).filter(Budget.category_key == "FOOD_AND_DRINK", Budget.month == "2026-07").one()
        assert float(b.limit) == 400.0
        p = s.query(Proposal).get(pid)
        assert p.status == "applied"
        assert p.undo["budget_existed"] is False
    finally:
        s.close()


def test_apply_updates_existing_budget(ctx):
    # Seed an existing budget — the common "change it" case.
    s = ctx.session()
    try:
        s.add(Budget(user_id=1, month="2026-07", category_name="Food & Drink",
                     category_key="FOOD_AND_DRINK", limit=550, color="#4fc4c4"))
        s.commit()
    finally:
        s.close()

    r = ctx.client.post("/api/proposals", json=_make_payload(basis_limit=550.0), headers=_svc_headers())
    pid = r.json()["id"]
    ap = ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx))
    assert ap.status_code == 200, ap.text
    body = ap.json()
    assert body["created"] is False
    assert body["prev_limit"] == 550.0
    assert body["new_limit"] == 400.0

    s = ctx.session()
    try:
        budgets = s.query(Budget).filter(Budget.category_key == "FOOD_AND_DRINK").all()
        assert len(budgets) == 1  # updated, not duplicated
        assert float(budgets[0].limit) == 400.0
    finally:
        s.close()


def test_apply_twice_conflicts(ctx):
    pid = ctx.client.post("/api/proposals", json=_make_payload(), headers=_svc_headers()).json()["id"]
    assert ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx)).status_code == 200
    assert ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx)).status_code == 409


# ── Dedup / supersede ─────────────────────────────────────────────────────────

def test_duplicate_pending_supersedes_old(ctx):
    p1 = ctx.client.post("/api/proposals", json=_make_payload(limit=400), headers=_svc_headers()).json()["id"]
    p2 = ctx.client.post("/api/proposals", json=_make_payload(limit=350), headers=_svc_headers()).json()["id"]

    lst = ctx.client.get("/api/proposals", headers=_auth_headers(ctx)).json()
    assert lst["pending_count"] == 1  # only the newer one remains pending
    assert lst["proposals"][0]["id"] == p2

    s = ctx.session()
    try:
        assert s.query(Proposal).get(p1).status == "superseded"
        assert s.query(Proposal).get(p1).superseded_by == p2
    finally:
        s.close()


# ── Dismiss ───────────────────────────────────────────────────────────────────

def test_dismiss(ctx):
    pid = ctx.client.post("/api/proposals", json=_make_payload(), headers=_svc_headers()).json()["id"]
    assert ctx.client.post(f"/api/proposals/{pid}/dismiss", headers=_auth_headers(ctx)).status_code == 200
    assert ctx.client.get("/api/proposals", headers=_auth_headers(ctx)).json()["pending_count"] == 0
    # Cannot apply a dismissed proposal
    assert ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx)).status_code == 409


# ── Undo with optimistic concurrency ──────────────────────────────────────────

def test_undo_restores_previous_limit(ctx):
    s = ctx.session()
    try:
        s.add(Budget(user_id=1, month="2026-07", category_name="Food & Drink",
                     category_key="FOOD_AND_DRINK", limit=550, color="#4fc4c4"))
        s.commit()
    finally:
        s.close()

    pid = ctx.client.post("/api/proposals", json=_make_payload(basis_limit=550.0), headers=_svc_headers()).json()["id"]
    ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx))
    assert ctx.client.post(f"/api/proposals/{pid}/undo", headers=_auth_headers(ctx)).status_code == 200

    s = ctx.session()
    try:
        b = s.query(Budget).filter(Budget.category_key == "FOOD_AND_DRINK").one()
        assert float(b.limit) == 550.0  # restored
        assert s.query(Proposal).get(pid).status == "undone"
    finally:
        s.close()


def test_undo_created_budget_deletes_it(ctx):
    pid = ctx.client.post("/api/proposals", json=_make_payload(), headers=_svc_headers()).json()["id"]
    ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx))
    assert ctx.client.post(f"/api/proposals/{pid}/undo", headers=_auth_headers(ctx)).status_code == 200
    s = ctx.session()
    try:
        assert s.query(Budget).filter(Budget.category_key == "FOOD_AND_DRINK").count() == 0
    finally:
        s.close()


def test_undo_refused_after_manual_edit(ctx):
    pid = ctx.client.post("/api/proposals", json=_make_payload(), headers=_svc_headers()).json()["id"]
    ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx))

    # Simulate the user manually changing the budget after applying.
    s = ctx.session()
    try:
        b = s.query(Budget).filter(Budget.category_key == "FOOD_AND_DRINK").one()
        b.limit = 999
        s.commit()
    finally:
        s.close()

    r = ctx.client.post(f"/api/proposals/{pid}/undo", headers=_auth_headers(ctx))
    assert r.status_code == 409  # refused rather than clobbering the manual edit


# ── Validation ────────────────────────────────────────────────────────────────

def test_unknown_category_key_rejected(ctx):
    r = ctx.client.post("/api/proposals", json=_make_payload(category_key="NONSENSE"), headers=_svc_headers())
    assert r.status_code == 422


def test_bad_month_rejected(ctx):
    r = ctx.client.post("/api/proposals", json=_make_payload(month="2026-13"), headers=_svc_headers())
    assert r.status_code == 422


def test_nonpositive_limit_rejected(ctx):
    r = ctx.client.post("/api/proposals", json=_make_payload(limit=0), headers=_svc_headers())
    assert r.status_code == 422


def test_raw_key_name_is_normalized(ctx):
    # Claude sometimes passes the raw key as the display name.
    r = ctx.client.post("/api/proposals", json=_make_payload(category_name="FOOD_AND_DRINK"),
                        headers=_svc_headers())
    assert r.status_code == 200
    assert r.json()["category_name"] == "Food & Drink"  # normalized to the label

    pid = r.json()["id"]
    ctx.client.post(f"/api/proposals/{pid}/apply", headers=_auth_headers(ctx))
    s = ctx.session()
    try:
        b = s.query(Budget).filter(Budget.category_key == "FOOD_AND_DRINK").one()
        assert b.category_name == "Food & Drink"  # budget saved with the nice label
    finally:
        s.close()
