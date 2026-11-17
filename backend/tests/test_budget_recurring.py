"""Recurring charges are reserved in the budget without a manual category."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.budgets_db import Budget, BudgetsBase
from app.models import Account, Base, Item, Transaction, User
from app.routes.budgets import MISC_BUDGET_CATEGORY, get_budget_items, is_planned_budget_line


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


def _charge(account, merchant, amount, when, **category):
    return Transaction(
        account=account,
        merchant=merchant,
        amount=Decimal(amount),
        date=when,
        pending=False,
        removed=False,
        hidden=False,
        **category,
    )


def _netflix(account, when, amount="15.00"):
    return _charge(
        account,
        "Netflix",
        amount,
        when,
        category_plaid="ENTERTAINMENT",
        category_plaid_detailed="ENTERTAINMENT_TV_AND_MOVIES",
    )


def _planned_limit(items) -> float:
    return round(
        sum(item.limit for item in items if is_planned_budget_line(item.virtual, item.recurring)),
        2,
    )


def test_recurring_charge_is_budgeted_when_category_is_not(sessions):
    ldb, bdb, checking = sessions
    ldb.add_all(
        [
            _netflix(checking, date(2026, 5, 1)),
            _netflix(checking, date(2026, 6, 1)),
            _netflix(checking, date(2026, 7, 1)),
            _charge(
                checking,
                "Cafe",
                "40.00",
                date(2026, 7, 2),
                category_plaid="FOOD_AND_DRINK",
                category_plaid_detailed="FOOD_AND_DRINK_RESTAURANT",
            ),
            _charge(
                checking,
                "Uber",
                "25.00",
                date(2026, 7, 3),
                category_plaid="TRANSPORTATION",
                category_plaid_detailed="TRANSPORTATION_TAXIS_AND_RIDE_SHARES",
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

    items = get_budget_items(bdb, ldb, "2026-07", as_of=date(2026, 7, 20))
    by_name = {item.category: item for item in items}

    assert by_name["Food & Drink"].spent == 40.0
    assert by_name["Food & Drink"].recurring is False
    netflix = by_name["Netflix"]
    assert netflix.recurring is True
    assert netflix.virtual is True
    assert netflix.limit == 15.0
    assert netflix.spent == 15.0
    assert by_name[MISC_BUDGET_CATEGORY].spent == 25.0
    assert _planned_limit(items) == 115.0
    assert sum(item.spent for item in items) == 80.0


def test_recurring_stays_inside_an_existing_category_budget(sessions):
    ldb, bdb, checking = sessions
    ldb.add_all(
        [
            _netflix(checking, date(2026, 5, 1)),
            _netflix(checking, date(2026, 6, 1)),
            _netflix(checking, date(2026, 7, 1)),
        ]
    )
    ldb.commit()
    bdb.add(
        Budget(
            user_id=1,
            month="2026-07",
            category_name="Entertainment",
            category_key="ENTERTAINMENT",
            limit=Decimal("40.00"),
            color="#e7705f",
        )
    )
    bdb.commit()

    items = get_budget_items(bdb, ldb, "2026-07", as_of=date(2026, 7, 20))
    assert all(not item.recurring for item in items)
    entertainment = next(item for item in items if item.category == "Entertainment")
    assert entertainment.spent == 15.0
    assert entertainment.limit == 40.0
    assert _planned_limit(items) == 40.0


def test_merchant_named_budget_keeps_the_recurring_spend(sessions):
    ldb, bdb, checking = sessions
    ldb.add_all(
        [
            _netflix(checking, date(2026, 5, 1)),
            _netflix(checking, date(2026, 6, 1)),
            _netflix(checking, date(2026, 7, 1)),
        ]
    )
    ldb.commit()
    bdb.add(
        Budget(
            user_id=1,
            month="2026-07",
            category_name="Netflix",
            category_key=None,
            limit=Decimal("20.00"),
            color="#e7705f",
        )
    )
    bdb.commit()

    items = get_budget_items(bdb, ldb, "2026-07", as_of=date(2026, 7, 20))
    assert [item.category for item in items] == ["Netflix"]
    assert items[0].recurring is False
    assert items[0].virtual is False
    assert items[0].spent == 15.0
    assert items[0].limit == 20.0


def test_recurring_budgets_appear_with_no_manual_budgets(sessions):
    ldb, bdb, checking = sessions
    ldb.add_all(
        [
            _netflix(checking, date(2026, 5, 1)),
            _netflix(checking, date(2026, 6, 1)),
            _netflix(checking, date(2026, 7, 1)),
            _charge(
                checking,
                "Cafe",
                "40.00",
                date(2026, 7, 2),
                category_plaid="FOOD_AND_DRINK",
            ),
        ]
    )
    ldb.commit()

    items = get_budget_items(bdb, ldb, "2026-07", as_of=date(2026, 7, 20))
    assert [item.category for item in items] == ["Netflix"]
    assert items[0].spent == 15.0
    assert items[0].limit == 15.0
    assert MISC_BUDGET_CATEGORY not in {item.category for item in items}


def test_upcoming_recurring_charge_is_reserved_before_it_posts(sessions):
    ldb, bdb, checking = sessions
    ldb.add_all(
        [
            _netflix(checking, date(2026, 5, 1)),
            _netflix(checking, date(2026, 6, 1)),
            _netflix(checking, date(2026, 7, 1)),
        ]
    )
    ldb.commit()

    items = get_budget_items(bdb, ldb, "2026-08", as_of=date(2026, 7, 20))
    assert len(items) == 1
    assert items[0].category == "Netflix"
    assert items[0].limit == 15.0
    assert items[0].spent == 0.0
    assert items[0].recurring is True


def test_lapsed_series_is_not_projected_into_later_months(sessions):
    ldb, bdb, checking = sessions
    ldb.add_all(
        [
            _netflix(checking, date(2026, 1, 5)),
            _netflix(checking, date(2026, 2, 5)),
            _netflix(checking, date(2026, 3, 5)),
        ]
    )
    ldb.commit()

    march = get_budget_items(bdb, ldb, "2026-03", as_of=date(2026, 11, 6))
    assert any(item.category == "Netflix" and item.spent == 15.0 for item in march)

    may = get_budget_items(bdb, ldb, "2026-05", as_of=date(2026, 11, 6))
    assert may == []


def test_repeating_loan_payments_are_not_budgeted(sessions):
    ldb, bdb, checking = sessions
    for when in (date(2026, 5, 4), date(2026, 6, 4), date(2026, 7, 4)):
        ldb.add(
            _charge(
                checking,
                "Chase Credit Card",
                "200.00",
                when,
                category_plaid="LOAN_PAYMENTS",
                category_plaid_detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
            )
        )
    ldb.commit()

    items = get_budget_items(bdb, ldb, "2026-07", as_of=date(2026, 7, 20))
    assert items == []


def test_weekly_series_reserves_each_occurrence(sessions):
    ldb, bdb, checking = sessions
    for day in (1, 8, 15, 22, 29):
        ldb.add(
            _charge(
                checking,
                "City Transit",
                "10.00",
                date(2026, 6, day),
                category_plaid="TRANSPORTATION",
                category_plaid_detailed="TRANSPORTATION_PUBLIC_TRANSIT",
            )
        )
    ldb.commit()

    items = get_budget_items(bdb, ldb, "2026-06", as_of=date(2026, 6, 30))
    assert len(items) == 1
    transit = items[0]
    assert transit.category == "City Transit"
    assert transit.recurring is True
    assert transit.limit == 50.0
    assert transit.spent == 50.0


def test_recurring_line_shows_over_when_the_charge_runs_high(sessions):
    ldb, bdb, checking = sessions
    ldb.add_all(
        [
            _netflix(checking, date(2026, 5, 1), "10.00"),
            _netflix(checking, date(2026, 6, 1), "10.00"),
            _netflix(checking, date(2026, 7, 1), "12.00"),
        ]
    )
    ldb.commit()

    items = get_budget_items(bdb, ldb, "2026-07", as_of=date(2026, 7, 20))
    netflix = items[0]
    assert netflix.recurring is True
    assert netflix.spent == 12.0
    assert netflix.limit < netflix.spent
