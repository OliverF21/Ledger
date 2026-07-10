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
