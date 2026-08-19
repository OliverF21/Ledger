"""Budget CRUD endpoint tests."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PLAID_CLIENT_ID", "test_client_id")
os.environ.setdefault("PLAID_SANDBOX_SECRET", "test_sandbox_secret")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import auth  # noqa: E402
from app.budgets_db import Budget, BudgetsBase, get_budgets_db  # noqa: E402
from app.database import Base as LedgerBase, get_db  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    budgets_engine = create_engine(
        f"sqlite:///{tmp_path / 'budgets.db'}",
        connect_args={"check_same_thread": False},
    )
    ledger_engine = create_engine(
        f"sqlite:///{tmp_path / 'ledger.db'}",
        connect_args={"check_same_thread": False},
    )
    BudgetsBase.metadata.create_all(budgets_engine)
    LedgerBase.metadata.create_all(ledger_engine)

    BudgetsSession = sessionmaker(bind=budgets_engine, autoflush=False, autocommit=False)
    LedgerSession = sessionmaker(bind=ledger_engine, autoflush=False, autocommit=False)

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

    import importlib
    import main

    importlib.reload(main)
    main.app.dependency_overrides[get_budgets_db] = _budgets_dep
    main.app.dependency_overrides[get_db] = _ledger_dep

    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c
    # Without this, these two overrides (bound to this test's throwaway
    # tmp_path engines) stay registered on `main.app` after the test ends.
    # `main` is only reloaded here and in test_auth.py, not by every test
    # file, so a LATER file that does a plain `import main` (no reload)
    # reuses this SAME app instance -- and if that file's own `Depends(get_db)`
    # happens to resolve to this exact (pre-reload) `get_db` object too, its
    # requests get silently routed through this already-torn-down database
    # instead of its own. Confirmed to actually happen: test_optimization_
    # settings_api.py's first test failed with a spurious NoResultFound on
    # the User row until this clear() was added.
    main.app.dependency_overrides.clear()


def _auth_headers():
    return {"Authorization": f"Bearer {auth.create_session_token(1)}"}


def test_delete_budget_removes_row(client):
    created = client.post(
        "/api/budgets",
        headers=_auth_headers(),
        json={
            "category_name": "Food & Drink",
            "category_key": "FOOD_AND_DRINK",
            "limit": 400,
            "month": "2026-07",
            "color": "#4fc4c4",
        },
    )
    assert created.status_code == 200
    budget_id = created.json()["id"]

    listed = client.get("/api/budgets?month=2026-07", headers=_auth_headers())
    assert listed.status_code == 200
    assert any(b["id"] == budget_id for b in listed.json()["budgets"])

    deleted = client.delete(f"/api/budgets/{budget_id}", headers=_auth_headers())
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True

    listed_after = client.get("/api/budgets?month=2026-07", headers=_auth_headers())
    assert listed_after.status_code == 200
    assert all(b["id"] != budget_id for b in listed_after.json()["budgets"])


def test_delete_missing_budget_returns_404(client):
    res = client.delete("/api/budgets/9999", headers=_auth_headers())
    assert res.status_code == 404


def test_budgets_carry_forward_into_empty_month(client):
    """A new month with no rows should inherit the prior month's limits."""
    created = client.post(
        "/api/budgets",
        headers=_auth_headers(),
        json={
            "category_name": "Food & Drink",
            "category_key": "FOOD_AND_DRINK",
            "limit": 400,
            "month": "2026-07",
            "color": "#4fc4c4",
        },
    )
    assert created.status_code == 200

    client.post(
        "/api/budgets",
        headers=_auth_headers(),
        json={
            "category_name": "Transportation",
            "category_key": "TRANSPORTATION",
            "limit": 200,
            "month": "2026-07",
            "color": "#8a7df0",
        },
    )

    august = client.get("/api/budgets?month=2026-08", headers=_auth_headers())
    assert august.status_code == 200
    body = august.json()
    assert body["month"] == "2026-08"
    by_name = {b["category"]: b for b in body["budgets"]}
    assert by_name["Food & Drink"]["limit"] == 400
    assert by_name["Transportation"]["limit"] == 200
    # Carried rows are real persisted copies, not just a virtual view.
    assert by_name["Food & Drink"]["id"] != created.json()["id"]

    july = client.get("/api/budgets?month=2026-07", headers=_auth_headers())
    assert len(july.json()["budgets"]) == 2


def test_budgets_do_not_overwrite_existing_month(client):
    client.post(
        "/api/budgets",
        headers=_auth_headers(),
        json={
            "category_name": "Food & Drink",
            "category_key": "FOOD_AND_DRINK",
            "limit": 400,
            "month": "2026-07",
            "color": "#4fc4c4",
        },
    )
    client.post(
        "/api/budgets",
        headers=_auth_headers(),
        json={
            "category_name": "Food & Drink",
            "category_key": "FOOD_AND_DRINK",
            "limit": 500,
            "month": "2026-08",
            "color": "#4fc4c4",
        },
    )

    august = client.get("/api/budgets?month=2026-08", headers=_auth_headers())
    assert august.status_code == 200
    budgets = august.json()["budgets"]
    assert len(budgets) == 1
    assert budgets[0]["limit"] == 500
