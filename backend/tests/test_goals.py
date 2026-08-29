"""Goals CRUD, labeled-transfer progress, and Cash Flow named sinks."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PLAID_CLIENT_ID", "test_client_id")
os.environ.setdefault("PLAID_SANDBOX_SECRET", "test_sandbox_secret")
if not os.environ.get("DATABASE_URL", "").startswith("sqlite"):
    os.environ["DATABASE_URL"] = "sqlite:///ledger.db"
if not os.environ.get("BUDGETS_DATABASE_URL", "sqlite:///budgets.db").startswith("sqlite"):
    os.environ["BUDGETS_DATABASE_URL"] = "sqlite:///budgets.db"

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, database  # noqa: E402
from app.budgets_db import BudgetsBase, FinancialGoal, get_budgets_db  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Account, Base, GoalAttribution, Item, Transaction, User  # noqa: E402
from app.services.analytics_service import build_cash_flow  # noqa: E402
from app.services.goals_service import (  # noqa: E402
    build_goal_progress,
    replace_txn_attributions,
    upsert_goal,
)
from app.txn_classifier import classify_cash_flow_txn  # noqa: E402


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("PROPOSAL_SERVICE_KEY", "unused-for-goals")
    budgets_engine = create_engine(
        f"sqlite:///{tmp_path / 'budgets.db'}", connect_args={"check_same_thread": False}
    )
    ledger_engine = create_engine(
        f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False}
    )
    BudgetsBase.metadata.create_all(budgets_engine)
    Base.metadata.create_all(ledger_engine)
    BudgetsSession = sessionmaker(bind=budgets_engine, autoflush=False, autocommit=False)
    LedgerSession = sessionmaker(bind=ledger_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", LedgerSession)

    import main  # noqa: E402

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

    app.dependency_overrides[get_budgets_db] = _budgets_dep
    app.dependency_overrides[get_db] = _ledger_dep
    token = auth.create_session_token(1)
    client = TestClient(app)

    class Ctx:
        pass

    c = Ctx()
    c.client = client
    c.token = token
    c.budgets = BudgetsSession
    c.ledger = LedgerSession
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


def _auth(ctx):
    return {"Authorization": f"Bearer {ctx.token}"}


def _seed_accounts(ledger: Session) -> tuple[Account, Account]:
    user = User(id=1, username="default_user")
    item = Item(user=user, item_id="item_1", institution_name="Bank", access_token_encrypted="x")
    checking = Account(
        item=item,
        plaid_account_id="chk",
        name="Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("4000"),
    )
    card = Account(
        item=item,
        plaid_account_id="card",
        name="Visa",
        type="credit",
        subtype="credit card",
        current_balance=Decimal("200"),
    )
    ledger.add_all([user, item, checking, card])
    ledger.flush()
    return checking, card


def test_classifier_savings_transfer():
    role = classify_cash_flow_txn(
        amount=500.0,
        category_user=None,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_SAVINGS",
        merchant="Ally",
        original_description="Transfer to savings",
        description_raw=None,
        transaction_code="transfer",
        payment_meta=None,
        counterparties=None,
        account_type="depository",
        account_subtype="checking",
    )
    assert role == "savings"


def test_goals_crud_and_progress(ctx):
    r = ctx.client.post(
        "/api/goals",
        json={
            "name": "Vacation",
            "kind": "sinking_fund",
            "target_amount": 5000,
            "current_amount": 1000,
            "monthly_contribution": 500,
        },
        headers=_auth(ctx),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Vacation"
    assert body["opening_amount"] == 1000.0
    assert body["progress"] == 1000.0
    assert body["percent_funded"] == 20.0
    gid = body["id"]

    lst = ctx.client.get("/api/goals", headers=_auth(ctx)).json()
    assert len(lst["goals"]) == 1

    patch = ctx.client.patch(
        f"/api/goals/{gid}",
        json={
            "name": "Vacation",
            "kind": "sinking_fund",
            "target_amount": 5000,
            "current_amount": 1000,
            "monthly_contribution": 400,
        },
        headers=_auth(ctx),
    )
    assert patch.status_code == 200
    assert patch.json()["monthly_contribution"] == 400.0


def test_labeling_does_not_change_category(ctx):
    ls = ctx.ledger()
    checking, _ = _seed_accounts(ls)
    txn = Transaction(
        account=checking,
        merchant="Ally Transfer",
        amount=Decimal("500.00"),
        date=date(2026, 6, 15),
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_SAVINGS",
        category_user=None,
        pending=False,
        removed=False,
        hidden=False,
    )
    ls.add(txn)
    ls.commit()
    txn_id = txn.id
    ls.close()

    goal = ctx.client.post(
        "/api/goals",
        json={"name": "Vacation", "kind": "sinking_fund", "target_amount": 5000, "current_amount": 0},
        headers=_auth(ctx),
    ).json()

    lab = ctx.client.put(
        f"/api/transactions/{txn_id}/goal-labels",
        json={"attributions": [{"goal_id": goal["id"], "amount": 500}]},
        headers=_auth(ctx),
    )
    assert lab.status_code == 200, lab.text

    txns = ctx.client.get("/api/transactions?limit=50", headers=_auth(ctx)).json()["transactions"]
    row = next(t for t in txns if t["id"] == txn_id)
    assert row["category_user"] is None
    assert row["goal_labels"][0]["name"] == "Vacation"
    assert row["goal_labels"][0]["amount"] == 500.0

    progress = ctx.client.get("/api/goals", headers=_auth(ctx)).json()["goals"][0]
    assert progress["labeled_in"] == 500.0
    assert progress["progress"] == 500.0


def test_cash_flow_named_sink_and_unallocated(ctx):
    ls = ctx.ledger()
    checking, card = _seed_accounts(ls)
    ls.add_all(
        [
            Transaction(
                account=checking,
                merchant="Employer",
                amount=Decimal("-3000.00"),
                date=date(2026, 6, 3),
                category_user="Paycheck",
                pending=False,
                removed=False,
                hidden=False,
            ),
            Transaction(
                account=card,
                merchant="Grocer",
                amount=Decimal("200.00"),
                date=date(2026, 6, 5),
                category_plaid="FOOD_AND_DRINK",
                pending=False,
                removed=False,
                hidden=False,
            ),
            Transaction(
                account=checking,
                merchant="Ally Transfer",
                amount=Decimal("500.00"),
                date=date(2026, 6, 10),
                category_plaid="TRANSFER_OUT",
                category_plaid_detailed="TRANSFER_OUT_SAVINGS",
                pending=False,
                removed=False,
                hidden=False,
            ),
            Transaction(
                account=checking,
                merchant="Vanguard",
                amount=Decimal("250.00"),
                date=date(2026, 6, 12),
                category_plaid="TRANSFER_OUT",
                category_plaid_detailed="TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS",
                pending=False,
                removed=False,
                hidden=False,
            ),
        ]
    )
    ls.commit()
    ally = ls.query(Transaction).filter(Transaction.merchant == "Ally Transfer").one()
    ls.close()

    bs = ctx.budgets()
    goal, _, _ = upsert_goal(
        bs, name="Vacation", kind="sinking_fund", target_amount=5000, current_amount=0
    )
    bs.commit()
    gid = goal.id
    ls = ctx.ledger()
    replace_txn_attributions(ls, bs, ally.id, [(gid, 500.0)])
    ls.commit()
    ls.close()
    bs.close()

    ls = ctx.ledger()
    bs = ctx.budgets()
    flow = build_cash_flow(ls, month="2026-06", goals_db=bs)
    spend_ids = {n.id for n in flow.spending_categories}
    alloc = {n.id: n for n in flow.allocation_nodes}
    assert "FOOD_AND_DRINK" in spend_ids or any("FOOD" in i for i in spend_ids)
    assert flow.total_spending == 200.0
    assert alloc[f"goal:{gid}"].label == "Vacation"
    assert alloc[f"goal:{gid}"].amount == 500.0
    assert alloc["Investments"].amount == 250.0
    assert "__savings__" not in alloc
    assert alloc["__unallocated__"].amount == 3000.0 - 200.0 - 500.0 - 250.0
    assert flow.savings == alloc["__unallocated__"].amount
    ls.close()
    bs.close()

    # REST includes allocation_nodes
    data = ctx.client.get("/api/analytics/cash-flow?month=2026-06", headers=_auth(ctx)).json()
    names = {n["label"] for n in data["allocation_nodes"]}
    assert "Vacation" in names
    assert "Investments" in names
    assert "Savings" in names


def test_progress_uses_labels_not_opening_only(ctx):
    ls = ctx.ledger()
    checking, _ = _seed_accounts(ls)
    txn = Transaction(
        account=checking,
        merchant="HYSA",
        amount=Decimal("200.00"),
        date=date(2026, 6, 1),
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_SAVINGS",
        pending=False,
        removed=False,
        hidden=False,
    )
    ls.add(txn)
    ls.commit()
    txn_id = txn.id
    ls.close()

    bs = ctx.budgets()
    goal, _, _ = upsert_goal(
        bs, name="Emergency", kind="emergency_fund", target_amount=10000, current_amount=2400
    )
    bs.commit()
    ls = ctx.ledger()
    replace_txn_attributions(ls, bs, txn_id, [(goal.id, 200.0)])
    ls.commit()
    progress = build_goal_progress(goal, ls)
    assert progress.opening_amount == 2400.0
    assert progress.labeled_in == 200.0
    assert progress.progress == 2600.0
    ls.close()
    bs.close()


def test_transactions_router_imports():
    from app.routes.transactions import SimilarTransaction, router

    assert router.prefix == "/transactions"
    assert SimilarTransaction.model_fields["merchant"]
