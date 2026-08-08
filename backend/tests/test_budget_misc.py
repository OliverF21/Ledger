"""Untracked spending should land in a virtual Misc. budget bucket."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.budgets_db import Budget, BudgetsBase
from app.models import Account, Base, Item, Transaction, User
from app.routes.budgets import MISC_BUDGET_CATEGORY, get_budget_items


@pytest.fixture()
def sessions(tmp_path):
    ledger_engine = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}")
    budgets_engine = create_engine(f"sqlite:///{tmp_path / 'budgets.db'}")
    Base.metadata.create_all(ledger_engine)
    BudgetsBase.metadata.create_all(budgets_engine)
    LedgerSession = sessionmaker(bind=ledger_engine, autoflush=False, autocommit=False)
    BudgetsSession = sessionmaker(bind=budgets_engine, autoflush=False, autocommit=False)

    ldb = LedgerSession()
    bdb = BudgetsSession()
    try:
        user = User(id=1, username="default_user")
        item = Item(
            user=user,
            item_id="item_1",
            institution_name="Test Bank",
            access_token_encrypted="encrypted",
        )
        checking = Account(
            item=item,
            plaid_account_id="acct_checking",
            name="Checking",
            type="depository",
            subtype="checking",
            current_balance=Decimal("2500.00"),
        )
        ldb.add_all([user, item, checking])
        ldb.flush()
        yield ldb, bdb, checking
    finally:
        ldb.close()
        bdb.close()


def test_untracked_spend_lands_in_misc_bucket(sessions):
    ldb, bdb, checking = sessions
    ldb.add_all(
        [
            Transaction(
                account=checking,
                merchant="Cafe",
                amount=Decimal("40.00"),
                date=date(2026, 7, 2),
                category_plaid="FOOD_AND_DRINK",
                category_plaid_detailed="FOOD_AND_DRINK_RESTAURANT",
                pending=False,
                removed=False,
                hidden=False,
            ),
            Transaction(
                account=checking,
                merchant="Uber",
                amount=Decimal("25.00"),
                date=date(2026, 7, 3),
                category_plaid="TRANSPORTATION",
                category_plaid_detailed="TRANSPORTATION_TAXIS_AND_RIDE_SHARES",
                pending=False,
                removed=False,
                hidden=False,
            ),
            Transaction(
                account=checking,
                merchant="Robinhood",
                amount=Decimal("500.00"),
                date=date(2026, 7, 4),
                category_plaid="TRANSFER_OUT",
                category_plaid_detailed="TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS",
                pending=False,
                removed=False,
                hidden=False,
            ),
        ]
    )
    ldb.commit()

    bdb.add(
        Budget(
            user_id=1,
            month="2026-07",
            category_name="Food & Drink",
            category_key="FOOD_AND_DRINK",
            limit=Decimal("100.00"),
            color="#4fc4c4",
        )
    )
    bdb.commit()

    items = get_budget_items(bdb, ldb, "2026-07")
    by_name = {item.category: item for item in items}

    assert by_name["Food & Drink"].spent == 40.0
    assert by_name["Food & Drink"].virtual is False
    assert MISC_BUDGET_CATEGORY in by_name
    misc = by_name[MISC_BUDGET_CATEGORY]
    assert misc.virtual is True
    assert misc.spent == 25.0  # Uber only; investment transfer excluded
    assert misc.limit == 0.0
    assert sum(item.spent for item in items) == 65.0


def test_misc_bucket_omitted_when_all_spend_is_tracked(sessions):
    ldb, bdb, checking = sessions
    ldb.add(
        Transaction(
            account=checking,
            merchant="Cafe",
            amount=Decimal("40.00"),
            date=date(2026, 7, 2),
            category_plaid="FOOD_AND_DRINK",
            category_plaid_detailed="FOOD_AND_DRINK_RESTAURANT",
            pending=False,
            removed=False,
            hidden=False,
        )
    )
    ldb.commit()
    bdb.add(
        Budget(
            user_id=1,
            month="2026-07",
            category_name="Food & Drink",
            category_key="FOOD_AND_DRINK",
            limit=Decimal("100.00"),
            color="#4fc4c4",
        )
    )
    bdb.commit()

    items = get_budget_items(bdb, ldb, "2026-07")
    assert all(not item.virtual for item in items)
    assert all(item.category != MISC_BUDGET_CATEGORY for item in items)


def test_name_only_primary_budget_matches_leaf_spend(sessions):
    """Manual 'Travel' budget (no category_key) still captures TRAVEL_FLIGHTS spend."""
    ldb, bdb, checking = sessions
    ldb.add(
        Transaction(
            account=checking,
            merchant="Airline",
            amount=Decimal("500.00"),
            date=date(2026, 7, 5),
            category_plaid="TRAVEL",
            category_plaid_detailed="TRAVEL_FLIGHTS",
            pending=False,
            removed=False,
            hidden=False,
        )
    )
    ldb.commit()
    bdb.add(
        Budget(
            user_id=1,
            month="2026-07",
            category_name="Travel",
            category_key=None,
            limit=Decimal("600.00"),
            color="#4ec38a",
        )
    )
    bdb.commit()

    items = get_budget_items(bdb, ldb, "2026-07")
    by_name = {item.category: item for item in items}
    assert by_name["Travel"].spent == 500.0
    assert MISC_BUDGET_CATEGORY not in by_name
