"""Integration tests across the matcher <-> classifier seam.

Each of app.transfer_matcher and app.txn_classifier was previously tested only
in isolation, which hid two real bugs that only appear when real ORM rows flow
from match_transfers() into classify_orm_transaction():

  1. A checking->savings transfer got matched, and the match check then fired
     BEFORE the savings-funding check, silently emptying the Savings cash-flow
     node.
  2. A manual category pick was overridden by the persisted match.

These tests run both halves together on real SQLAlchemy rows.
"""

from __future__ import annotations

import os
from datetime import date

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import Account, InvestmentTransaction, Item, Transaction, User  # noqa: E402
from app.transfer_matcher import match_transfers  # noqa: E402
from app.txn_classifier import classify_orm_transaction  # noqa: E402

TODAY = date(2026, 8, 24)
TXN_DATE = date(2026, 8, 14)


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def accounts(db):
    """checking / savings / credit / investment accounts under one Item."""
    user = User(username="tester", password_hash="x")
    db.add(user)
    db.flush()
    item = Item(user_id=user.id, item_id="item_1", access_token_encrypted="enc")
    db.add(item)
    db.flush()

    made = {}
    for key, name, type_, subtype in [
        ("checking", "Checking", "depository", "checking"),
        ("savings", "Savings", "depository", "savings"),
        ("credit", "Gold Card", "credit", "credit card"),
        ("brokerage", "Brokerage", "investment", "brokerage"),
    ]:
        acct = Account(
            item_id=item.id,
            plaid_account_id=f"plaid_{key}",
            name=name,
            type=type_,
            subtype=subtype,
        )
        db.add(acct)
        made[key] = acct
    db.commit()
    return made


def _txn(account: Account, **overrides) -> Transaction:
    defaults = dict(
        account_id=account.id,
        merchant="Online Transfer",
        amount=500.0,
        date=TXN_DATE,
        pending=False,
        removed=False,
        hidden=False,
        manual_override=False,
        transaction_code="transfer",
    )
    defaults.update(overrides)
    return Transaction(**defaults)


# ── Fix 1: checking -> savings keeps the "savings" role ───────────────────────


def test_checking_to_savings_transfer_classifies_as_savings(db, accounts):
    """Regression test for the savings/transfer priority bug.

    Savings accounts are depository, so a checking->savings transfer produces
    two real Transaction rows and the matcher correctly pairs them. The match
    signal must NOT pre-empt the savings-funding check, or the Savings
    cash-flow node silently empties out for anyone with a linked savings
    account.
    """
    checking_out = _txn(
        accounts["checking"],
        amount=500.0,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_SAVINGS",
    )
    savings_in = _txn(
        accounts["savings"],
        amount=-500.0,
        category_plaid="TRANSFER_IN",
        category_plaid_detailed="TRANSFER_IN_SAVINGS",
    )
    db.add_all([checking_out, savings_in])
    db.commit()

    stats = match_transfers(db, today=TODAY)
    assert stats["transfer_pairs"] == 1

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == savings_in.id

    # The match is real, but the outflow leg is still savings funding.
    assert classify_orm_transaction(checking_out, account=accounts["checking"]) == "savings"


def test_savings_role_survives_match_via_account_subtype_only(db, accounts):
    """Same as above, but the savings signal comes from the destination
    account's subtype rather than a TRANSFER_OUT_SAVINGS detailed category."""
    checking_out = _txn(
        accounts["checking"],
        amount=500.0,
        merchant="Transfer to Savings",
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
    )
    savings_in = _txn(
        accounts["savings"],
        amount=-500.0,
        category_plaid="TRANSFER_IN",
        category_plaid_detailed="TRANSFER_IN_ACCOUNT_TRANSFER",
    )
    db.add_all([checking_out, savings_in])
    db.commit()

    match_transfers(db, today=TODAY)
    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id is not None

    assert classify_orm_transaction(checking_out, account=accounts["checking"]) == "savings"


# ── Fix 2: manual override beats the match signal ─────────────────────────────


def test_manual_override_beats_matched_transfer(db, accounts):
    """A user who explicitly categorized a matched outflow as spending keeps
    that role — the persisted match must not force it to "transfer".

    transaction_code is left None on the overridden leg so the pre-existing
    "transaction_code == transfer" fallback can't account for the result; the
    counterpart leg alone carries the signal that clears the matcher's
    transferish precondition.
    """
    checking_out = _txn(
        accounts["checking"],
        amount=500.0,
        merchant="Unlabeled ACH",
        category_user="Shopping",
        manual_override=True,
        transaction_code=None,
    )
    other_in = _txn(accounts["credit"], amount=-500.0, merchant="Unlabeled ACH")
    db.add_all([checking_out, other_in])
    db.commit()

    match_transfers(db, today=TODAY)
    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == other_in.id

    assert classify_orm_transaction(checking_out, account=accounts["checking"]) == "spending"

    # Same row without the override: the match signal DOES win, proving the
    # assertion above is exercising the manual_override gate.
    checking_out.manual_override = False
    assert classify_orm_transaction(checking_out, account=accounts["checking"]) == "transfer"


def test_manual_override_beats_matched_investment(db, accounts):
    checking_out = _txn(
        accounts["checking"],
        amount=500.0,
        merchant="Unlabeled ACH",
        category_user="Shopping",
        manual_override=True,
        transaction_code=None,
    )
    deposit = InvestmentTransaction(
        account_id=accounts["brokerage"].id,
        plaid_investment_transaction_id="itx_manual",
        name="ACH deposit",
        type="cash",
        subtype="deposit",
        amount=-500.0,
        date=TXN_DATE,
    )
    db.add_all([checking_out, deposit])
    db.commit()

    match_transfers(db, today=TODAY)
    db.refresh(checking_out)
    assert checking_out.transfer_match_investment_txn_id == deposit.id

    assert classify_orm_transaction(checking_out, account=accounts["checking"]) == "spending"

    checking_out.manual_override = False
    assert classify_orm_transaction(checking_out, account=accounts["checking"]) == "investments"


def test_matched_inflow_without_manual_override_still_classifies_as_transfer(db, accounts):
    """Guard against over-correcting Fix 2: with manual_override False the
    match must still win on the inflow leg."""
    checking_out = _txn(accounts["checking"], amount=500.0, merchant="Unlabeled ACH")
    other_in = _txn(accounts["credit"], amount=-500.0, merchant="Unlabeled ACH")
    db.add_all([checking_out, other_in])
    db.commit()

    match_transfers(db, today=TODAY)
    db.refresh(other_in)

    # The credit leg would hit _looks_like_card_payment anyway; use the
    # depository-side inflow shape to isolate the match signal.
    assert classify_orm_transaction(other_in, account=accounts["checking"]) == "transfer"


# ── The original scenario this feature exists to fix ──────────────────────────


def test_no_text_cue_transfer_pair_both_legs_classify_as_transfer(db, accounts):
    """Two bank legs with no merchant/category cues at all: only the persisted
    match tells us these are transfers. Both legs must classify as "transfer"."""
    checking_out = _txn(
        accounts["checking"], amount=500.0, merchant="Unlabeled ACH", category_plaid=None
    )
    counterpart_in = _txn(
        accounts["savings"], amount=-500.0, merchant="Unlabeled ACH", category_plaid=None
    )
    db.add_all([checking_out, counterpart_in])
    db.commit()

    match_transfers(db, today=TODAY)
    db.refresh(checking_out)
    db.refresh(counterpart_in)
    assert checking_out.transfer_match_transaction_id == counterpart_in.id

    # Classify both against a plain checking account so neither the credit-card
    # nor the savings-subtype heuristic can account for the result.
    assert classify_orm_transaction(checking_out, account=accounts["checking"]) == "transfer"
    assert classify_orm_transaction(counterpart_in, account=accounts["checking"]) == "transfer"


def test_investment_funding_pair_classifies_bank_leg_as_investments(db, accounts):
    """A bank outflow matched to an investment cash deposit classifies as
    "investments". Note the bank<->bank transferish precondition does NOT
    apply to this path (the investment pool is already restricted to external
    cash-flow types/subtypes), but a realistic Plaid transaction_code is set
    here anyway."""
    checking_out = _txn(
        accounts["checking"],
        amount=500.0,
        merchant="Unlabeled ACH",
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
    )
    deposit = InvestmentTransaction(
        account_id=accounts["brokerage"].id,
        plaid_investment_transaction_id="itx_funding",
        name="ACH deposit",
        type="cash",
        subtype="deposit",
        amount=-500.0,
        date=TXN_DATE,
    )
    db.add_all([checking_out, deposit])
    db.commit()

    stats = match_transfers(db, today=TODAY)
    assert stats["investment_pairs"] == 1

    db.refresh(checking_out)
    db.refresh(deposit)
    assert checking_out.transfer_match_investment_txn_id == deposit.id
    assert deposit.matched_transaction_id == checking_out.id

    assert classify_orm_transaction(checking_out, account=accounts["checking"]) == "investments"


def test_unmatched_coffee_purchase_stays_spending(db, accounts):
    """End-to-end counterpart to the transferish-precondition unit test: the
    coffee and the unrelated refund must both keep their real roles."""
    coffee = _txn(
        accounts["checking"],
        amount=8.25,
        date=TXN_DATE,
        merchant="Blue Bottle",
        category_plaid="FOOD_AND_DRINK",
        category_plaid_detailed="FOOD_AND_DRINK_COFFEE",
        transaction_code=None,
    )
    refund = _txn(
        accounts["savings"],
        amount=-4.10,
        date=date(2026, 8, 17),
        merchant="Target",
        category_plaid="GENERAL_MERCHANDISE",
        category_plaid_detailed="GENERAL_MERCHANDISE_OTHER",
        transaction_code=None,
    )
    db.add_all([coffee, refund])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(coffee)
    db.refresh(refund)
    assert coffee.transfer_match_transaction_id is None
    assert refund.transfer_match_transaction_id is None
    assert classify_orm_transaction(coffee, account=accounts["checking"]) == "spending"
    assert classify_orm_transaction(refund, account=accounts["checking"]) == "income"


# ── Sync call sites actually invoke the matcher ───────────────────────────────


def test_scheduler_sync_all_items_runs_the_matcher(db, monkeypatch):
    """app.scheduler.sync_all_items() must call match_transfers once, after the
    per-item loop."""
    from unittest.mock import MagicMock

    from app import budgets_db, crypto_sync, database, notifications, scheduler, sync_engine
    from app import transfer_matcher

    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(budgets_db, "BudgetsSessionLocal", lambda: MagicMock())
    monkeypatch.setattr(notifications, "notify_new_alerts", lambda *a, **k: None)
    monkeypatch.setattr(sync_engine, "get_real_items", lambda _db: [])
    monkeypatch.setattr(sync_engine, "sync_item", lambda *a, **k: {"synced": 0, "removed": 0})
    monkeypatch.setattr(crypto_sync, "sync_crypto_wallets", lambda _db: {"skipped": True})

    matcher = MagicMock(return_value={"transfer_pairs": 0, "investment_pairs": 0})
    monkeypatch.setattr(transfer_matcher, "match_transfers", matcher)

    scheduler.sync_all_items()

    matcher.assert_called_once()


@pytest.fixture()
def client(db, monkeypatch):
    from fastapi.testclient import TestClient

    import main
    from app import database
    from app.auth import require_auth

    main.app.dependency_overrides[require_auth] = lambda: 1
    main.app.dependency_overrides[database.get_db] = lambda: db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_plaid_sync_endpoint_runs_the_matcher(client, monkeypatch):
    """POST /api/plaid/sync must call match_transfers once."""
    from unittest.mock import MagicMock

    from app import transfer_matcher
    from app.plaid_service import PlaidService
    from app.routes import plaid as plaid_routes

    monkeypatch.setattr(PlaidService, "is_configured", staticmethod(lambda: True))
    monkeypatch.setattr(plaid_routes, "get_real_items", lambda _db: [])

    matcher = MagicMock(return_value={"transfer_pairs": 0, "investment_pairs": 0})
    monkeypatch.setattr(transfer_matcher, "match_transfers", matcher)

    resp = client.post("/api/plaid/sync")

    assert resp.status_code == 200
    matcher.assert_called_once()


def test_investments_refresh_endpoint_runs_the_matcher(client, monkeypatch):
    """POST /api/investments/refresh must call match_transfers once."""
    from unittest.mock import MagicMock

    from app import transfer_matcher
    from app.routes import investments as investments_routes

    monkeypatch.setattr(investments_routes, "get_real_items", lambda _db: [])

    matcher = MagicMock(return_value={"transfer_pairs": 0, "investment_pairs": 0})
    monkeypatch.setattr(transfer_matcher, "match_transfers", matcher)

    resp = client.post("/api/investments/refresh")

    assert resp.status_code == 200
    matcher.assert_called_once()
