from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Account, Base, Item, Transaction, User
from app.services import tvm
from app.services.goals_planning_service import (
    SpendCut,
    build_planning_capacity,
    plan_goal,
    plan_goal_from_expenses,
)
from mcp_server import server as mcp_server_module


TODAY = date(2026, 8, 27)


@pytest.fixture
def db_session(tmp_path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'goals-ledger.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
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
        session.add_all([user, item, checking])
        session.flush()

        def paycheck(month_day: date) -> Transaction:
            return Transaction(
                account=checking,
                merchant="Employer Inc",
                amount=Decimal("-3000.00"),
                date=month_day,
                category_user="Paycheck",
                pending=False,
                removed=False,
                hidden=False,
            )

        def spend(month_day: date, amount: str, *, plaid: str, merchant: str) -> Transaction:
            return Transaction(
                account=checking,
                merchant=merchant,
                amount=Decimal(amount),
                date=month_day,
                category_plaid=plaid,
                pending=False,
                removed=False,
                hidden=False,
            )

        session.add_all(
            [
                paycheck(date(2026, 3, 1)),
                spend(date(2026, 3, 5), "2000.00", plaid="RENT_AND_UTILITIES", merchant="Landlord"),
                paycheck(date(2026, 4, 1)),
                spend(date(2026, 4, 5), "2400.00", plaid="RENT_AND_UTILITIES", merchant="Landlord"),
                paycheck(date(2026, 5, 1)),
                spend(date(2026, 5, 5), "2200.00", plaid="RENT_AND_UTILITIES", merchant="Landlord"),
                paycheck(date(2026, 6, 1)),
                spend(date(2026, 6, 5), "2100.00", plaid="RENT_AND_UTILITIES", merchant="Landlord"),
                spend(
                    date(2026, 6, 8),
                    "400.00",
                    plaid="FOOD_AND_DRINK",
                    merchant="Neighborhood Cafe",
                ),
            ]
        )
        session.commit()
        yield session
    finally:
        session.close()


def test_capacity_uses_min_of_current_and_lookback(db_session: Session):
    capacity = build_planning_capacity(
        db_session,
        lookback_months=3,
        month="2026-06",
        today=TODAY,
    )
    assert capacity.residual_this_month == 500.0
    assert capacity.residual_lookback_avg == 800.0
    assert capacity.recommended_available == 500.0
    assert capacity.policy == "min(current, lookback)"
    assert any("lower current" in note.lower() for note in capacity.notes)


def test_capacity_skips_min_for_partial_current_month(db_session: Session):
    capacity = build_planning_capacity(
        db_session,
        lookback_months=3,
        month="2026-08",
        today=TODAY,
    )
    assert capacity.residual_this_month == 0.0
    assert capacity.series[-1].is_partial is True
    assert capacity.recommended_available == capacity.residual_lookback_avg
    assert any("in progress" in note.lower() for note in capacity.notes)


def test_plan_goal_time_to_goal_from_capacity(db_session: Session):
    plan = plan_goal(
        db_session,
        target_amount=10000,
        current_amount=2400,
        mode="time_to_goal",
        month="2026-06",
        today=TODAY,
    )
    assert plan.monthly_contribution == 500.0
    assert plan.months == 16
    assert plan.affordable is True
    assert plan.annual_return == 0.0
    assert plan.schedule_summary
    assert plan.projected_end_month == "2027-11"


def test_plan_goal_required_contribution_unaffordable(db_session: Session):
    plan = plan_goal(
        db_session,
        target_amount=10000,
        current_amount=0,
        mode="required_contribution",
        months=6,
        month="2026-06",
        today=TODAY,
    )
    assert plan.monthly_contribution == 1666.67
    assert plan.affordable is False
    assert plan.months == 6


def test_plan_goal_invest_path_with_assumed_return():
    plan = plan_goal(
        None,
        target_amount=50000,
        current_amount=0,
        mode="required_contribution",
        months=60,
        annual_return=0.05,
        assumed_monthly_capacity=800,
        today=TODAY,
    )
    expected = tvm.pmt(pv=0, fv_target=50000, n=60, monthly_rate=0.05 / 12)
    assert plan.monthly_contribution == expected
    assert any("5.0%" in line for line in plan.assumptions)
    assert any("not a forecast" in line.lower() for line in plan.assumptions)


def test_plan_goal_from_expenses_cut_shortens_horizon(db_session: Session):
    plan = plan_goal_from_expenses(
        db_session,
        target_amount=10000,
        current_amount=2400,
        mode="time_to_goal",
        month="2026-06",
        today=TODAY,
        cuts=[SpendCut(monthly_delta=-150, category_key="FOOD_AND_DRINK")],
    )
    assert plan.contribution_before_cuts == 500.0
    assert plan.months_before_cuts == 16
    assert plan.monthly_contribution == 650.0
    assert plan.months == 12
    assert plan.cuts[0].matched is True
    assert plan.cuts[0].category_key == "FOOD_AND_DRINK"


def test_mcp_plan_goal_does_not_need_db():
    async def _check() -> None:
        result = await mcp_server_module.mcp.call_tool(
            "plan_goal",
            {
                "target_amount": 10000,
                "current_amount": 2000,
                "mode": "time_to_goal",
                "monthly_contribution": 800,
                "assumed_monthly_capacity": 800,
                "annual_return": 0,
            },
        )
        data = result.structured_content
        assert data is not None
        assert data["months"] == 10
        assert data["monthly_contribution"] == 800.0
        assert data["affordable"] is True
        assert data["assumptions"]

    asyncio.run(_check())


def test_mcp_planning_capacity_and_expense_plan(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    @contextmanager
    def fake_ledger_session():
        yield db_session

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return TODAY

    monkeypatch.setattr(mcp_server_module, "ledger_session", fake_ledger_session)
    monkeypatch.setattr("app.services.goals_planning_service.date", FrozenDate)

    async def _check() -> None:
        capacity = await mcp_server_module.mcp.call_tool(
            "planning_capacity",
            {"month": "2026-06", "lookback_months": 3},
        )
        cap = capacity.structured_content
        assert cap is not None
        assert cap["recommended_available"] == 500.0
        assert cap["policy"] == "min(current, lookback)"

        plan = await mcp_server_module.mcp.call_tool(
            "plan_goal_from_expenses",
            {
                "target_amount": 10000,
                "current_amount": 2400,
                "mode": "time_to_goal",
                "month": "2026-06",
                "cuts": [{"category_key": "FOOD_AND_DRINK", "monthly_delta": -150}],
            },
        )
        data = plan.structured_content
        assert data is not None
        assert data["monthly_contribution"] == 650.0
        assert data["months"] == 12
        assert data["months_before_cuts"] == 16

    asyncio.run(_check())


def test_mcp_instructions_forbid_homemade_tvm():
    text = mcp_server_module.mcp.instructions or ""
    assert "NPER/PMT/FV" in text
    assert "planning_capacity" in text
    assert "plan_goal_from_expenses" in text
