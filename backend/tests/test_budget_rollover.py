"""Unspent and overspent budget amounts roll into the next month."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.budgets_db import Budget, BudgetsBase
from app.models import Account, Base, Item, Transaction, User
from app.routes.budgets import get_budget_items, spendable_amount


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


def _budget(bdb, month: str, name: str, key: str, limit: str) -> Budget:
    row = Budget(
        user_id=1,
        month=month,
        category_name=name,
        category_key=key,
        limit=Decimal(limit),
        color="#4fc4c4",
    )
    bdb.add(row)
    bdb.commit()
    return row


def _spend(ldb, account, amount: str, when: date, primary: str) -> None:
    ldb.add(
        Transaction(
            account=account,
            merchant="Shop",
            amount=Decimal(amount),
            date=when,
            category_plaid=primary,
            category_plaid_detailed=f"{primary}_OTHER",
            pending=False,
            removed=False,
            hidden=False,
        )
    )
    ldb.commit()


def _by_name(items):
    return {item.category: item for item in items if not item.virtual}


def test_unspent_rolls_forward_and_limit_stays_the_plan(sessions):
    ldb, bdb, checking = sessions
    _budget(bdb, "2026-07", "Food & Drink", "FOOD_AND_DRINK", "400.00")
    _spend(ldb, checking, "100.00", date(2026, 7, 4), "FOOD_AND_DRINK")

    july = _by_name(get_budget_items(bdb, ldb, "2026-07"))
    assert july["Food & Drink"].rollover == 0
    assert july["Food & Drink"].spent == 100

    august = _by_name(get_budget_items(bdb, ldb, "2026-08"))
    food = august["Food & Drink"]
    assert food.limit == 400
    assert food.rollover == 300
    assert food.spent == 0
    assert spendable_amount(food.limit, food.rollover) == 700

    stored = bdb.query(Budget).filter(Budget.month == "2026-08").one()
    assert float(stored.limit) == 400


def test_overspend_reduces_next_month(sessions):
    ldb, bdb, checking = sessions
    _budget(bdb, "2026-07", "Food & Drink", "FOOD_AND_DRINK", "400.00")
    _spend(ldb, checking, "450.00", date(2026, 7, 4), "FOOD_AND_DRINK")

    august = _by_name(get_budget_items(bdb, ldb, "2026-08"))
    food = august["Food & Drink"]
    assert food.limit == 400
    assert food.rollover == -50
    assert spendable_amount(food.limit, food.rollover) == 350


def test_rollover_chains_and_follows_each_months_limit(sessions):
    ldb, bdb, checking = sessions
    _budget(bdb, "2026-07", "Food & Drink", "FOOD_AND_DRINK", "400.00")
    _spend(ldb, checking, "100.00", date(2026, 7, 4), "FOOD_AND_DRINK")
    _budget(bdb, "2026-08", "Food & Drink", "FOOD_AND_DRINK", "250.00")
    _spend(ldb, checking, "450.00", date(2026, 8, 4), "FOOD_AND_DRINK")

    august = _by_name(get_budget_items(bdb, ldb, "2026-08"))
    # July left 300; August's own limit does not change that incoming rollover.
    assert august["Food & Drink"].limit == 250
    assert august["Food & Drink"].rollover == 300
    assert august["Food & Drink"].spent == 450

    september = _by_name(get_budget_items(bdb, ldb, "2026-09"))
    food = september["Food & Drink"]
    # August could spend 250 + 300 = 550, spent 450, so 100 remains.
    assert food.limit == 250
    assert food.rollover == 100
    assert food.spent == 0


def test_unopened_month_still_consumes_the_carried_budget(sessions):
    ldb, bdb, checking = sessions
    _budget(bdb, "2026-07", "Food & Drink", "FOOD_AND_DRINK", "400.00")
    _spend(ldb, checking, "100.00", date(2026, 7, 4), "FOOD_AND_DRINK")
    _spend(ldb, checking, "50.00", date(2026, 8, 4), "FOOD_AND_DRINK")

    september = _by_name(get_budget_items(bdb, ldb, "2026-09"))
    food = september["Food & Drink"]
    # July left 300. August kept the $400 plan, so 700 was available and $50 was spent.
    assert food.limit == 400
    assert food.rollover == 650
    assert bdb.query(Budget).filter(Budget.month == "2026-08").count() == 0


def test_new_category_and_removed_category(sessions):
    ldb, bdb, checking = sessions
    _budget(bdb, "2026-07", "Food & Drink", "FOOD_AND_DRINK", "400.00")
    _budget(bdb, "2026-07", "Transportation", "TRANSPORTATION", "200.00")
    _spend(ldb, checking, "100.00", date(2026, 7, 4), "FOOD_AND_DRINK")
    _budget(bdb, "2026-08", "Transportation", "TRANSPORTATION", "200.00")
    _budget(bdb, "2026-08", "Shopping", "GENERAL_MERCHANDISE", "80.00")
    _spend(ldb, checking, "50.00", date(2026, 8, 4), "TRANSPORTATION")

    august = _by_name(get_budget_items(bdb, ldb, "2026-08"))
    assert "Food & Drink" not in august
    assert august["Shopping"].rollover == 0
    assert august["Transportation"].rollover == 200

    september = _by_name(get_budget_items(bdb, ldb, "2026-09"))
    assert "Food & Drink" not in september
    # August's unused $80 shopping budget arrives in September; the $80 plan is separate.
    assert september["Shopping"].limit == 80
    assert september["Shopping"].rollover == 80
    # July left $200. August's plan was $200 and $50 was spent, so $350 remains.
    assert september["Transportation"].limit == 200
    assert september["Transportation"].rollover == 350


def test_misc_spending_does_not_roll_into_a_category(sessions):
    ldb, bdb, checking = sessions
    _budget(bdb, "2026-07", "Food & Drink", "FOOD_AND_DRINK", "100.00")
    _spend(ldb, checking, "40.00", date(2026, 7, 2), "FOOD_AND_DRINK")
    _spend(ldb, checking, "25.00", date(2026, 7, 3), "TRANSPORTATION")

    july = get_budget_items(bdb, ldb, "2026-07")
    misc = next(item for item in july if item.virtual)
    assert misc.spent == 25
    assert misc.rollover == 0

    august = _by_name(get_budget_items(bdb, ldb, "2026-08"))
    assert august["Food & Drink"].rollover == 60
    assert all(not item.virtual for item in get_budget_items(bdb, ldb, "2026-08"))
