from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

if not os.environ.get("DATABASE_URL", "").startswith("sqlite"):
    os.environ["DATABASE_URL"] = "sqlite:///ledger.db"
if not os.environ.get("BUDGETS_DATABASE_URL", "sqlite:///budgets.db").startswith("sqlite"):
    os.environ["BUDGETS_DATABASE_URL"] = "sqlite:///budgets.db"

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.budgets_db import Budget, BudgetsBase
from app.models import Account, BalanceSnapshot, Base, Holding, Item, Security, Transaction, User
from app.routes.analytics import get_monthly_summary
from app.services.analytics_service import (
    build_budget_vs_actual,
    build_cash_flow,
    build_monthly_summary,
    build_net_worth,
    build_recurring_spend,
    get_spending_by_category,
    search_transactions,
)
from app.services.investment_service import build_investment_performance
from mcp_server import server as mcp_server_module
from mcp_server.sankey import build_cash_flow_sankey_payload, build_cash_flow_sankey_svg


import pytest


@pytest.fixture
def db_session(tmp_path) -> Session:
    db_path = tmp_path / "test-ledger.db"
    engine = create_engine(f"sqlite:///{db_path}")
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
        card = Account(
            item=item,
            plaid_account_id="acct_card",
            name="Visa",
            type="credit",
            subtype="credit card",
            current_balance=Decimal("500.00"),
        )
        brokerage_item = Item(
            user=user,
            item_id="invest_1",
            institution_name="Brokerage",
            access_token_encrypted="encrypted-invest",
        )
        brokerage = Account(
            item=brokerage_item,
            plaid_account_id="acct_brokerage",
            name="Brokerage",
            type="investment",
            subtype="brokerage",
            current_balance=Decimal("1200.00"),
        )

        session.add_all([user, item, checking, card, brokerage_item, brokerage])
        session.flush()

        security = Security(
            plaid_security_id="sec_1",
            ticker_symbol="VTI",
            name="Vanguard Total Market ETF",
            type="etf",
            close_price=Decimal("120.00"),
            iso_currency_code="USD",
        )
        session.add(security)
        session.flush()

        session.add(
            Holding(
                account=brokerage,
                security=security,
                quantity=Decimal("10.000000"),
                institution_price=Decimal("120.00"),
                institution_value=Decimal("1200.00"),
                cost_basis=Decimal("1000.00"),
                iso_currency_code="USD",
            )
        )
        session.add(BalanceSnapshot(account=brokerage, balance=Decimal("1000.00"), snapshot_date=date(2026, 6, 1)))

        session.add_all(
            [
                Transaction(
                    account=checking,
                    merchant="Employer Inc",
                    amount=Decimal("-3000.00"),
                    date=date(2026, 6, 3),
                    category_user="Paycheck",
                    pending=False,
                    removed=False,
                    hidden=False,
                ),
                Transaction(
                    account=card,
                    merchant="Corner Market",
                    amount=Decimal("120.00"),
                    date=date(2026, 6, 5),
                    category_plaid="FOOD_AND_DRINK",
                    category_plaid_detailed="FOOD_AND_DRINK_GROCERIES",
                    pending=False,
                    removed=False,
                    hidden=False,
                ),
                Transaction(
                    account=card,
                    merchant="Neighborhood Cafe",
                    amount=Decimal("200.00"),
                    date=date(2026, 6, 11),
                    category_plaid="FOOD_AND_DRINK",
                    category_user="Dining Out",
                    user_split_pct=Decimal("0.5000"),
                    pending=False,
                    removed=False,
                    hidden=False,
                ),
                Transaction(
                    account=card,
                    merchant="Neighborhood Cafe",
                    amount=Decimal("80.00"),
                    date=date(2026, 5, 18),
                    category_plaid="FOOD_AND_DRINK",
                    category_user="Dining Out",
                    pending=False,
                    removed=False,
                    hidden=False,
                ),
                Transaction(
                    account=card,
                    merchant="Pending Purchase",
                    amount=Decimal("999.00"),
                    date=date(2026, 6, 13),
                    category_user="Shopping",
                    pending=True,
                    removed=False,
                    hidden=False,
                ),
                Transaction(
                    account=card,
                    merchant="Hidden Purchase",
                    amount=Decimal("75.00"),
                    date=date(2026, 6, 12),
                    category_user="Shopping",
                    pending=False,
                    removed=False,
                    hidden=True,
                ),
                Transaction(
                    account=card,
                    merchant="Removed Purchase",
                    amount=Decimal("50.00"),
                    date=date(2026, 6, 12),
                    category_user="Shopping",
                    pending=False,
                    removed=True,
                    hidden=False,
                ),
                Transaction(
                    account=card,
                    merchant="Netflix 1234",
                    amount=Decimal("15.00"),
                    date=date(2026, 2, 1),
                    category_user="Streaming",
                    pending=False,
                    removed=False,
                    hidden=False,
                ),
                Transaction(
                    account=card,
                    merchant="Netflix 5678",
                    amount=Decimal("15.00"),
                    date=date(2026, 3, 3),
                    category_user="Streaming",
                    pending=False,
                    removed=False,
                    hidden=False,
                ),
                Transaction(
                    account=card,
                    merchant="Netflix 9012",
                    amount=Decimal("15.00"),
                    date=date(2026, 4, 2),
                    category_user="Streaming",
                    pending=False,
                    removed=False,
                    hidden=False,
                ),
            ]
        )
        session.commit()
        yield session
    finally:
        session.close()


@pytest.fixture
def budgets_session(tmp_path) -> Session:
    db_path = tmp_path / "test-budgets.db"
    engine = create_engine(f"sqlite:///{db_path}")
    BudgetsBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session = SessionLocal()
    try:
        session.add_all(
            [
                Budget(
                    user_id=1,
                    month="2026-06",
                    category_name="Travel",
                    category_key=None,
                    limit=Decimal("150.00"),
                    color="#4fc4c4",
                ),
                Budget(
                    user_id=1,
                    month="2026-06",
                    category_name="Dining Out",
                    category_key=None,
                    limit=Decimal("90.00"),
                    color="#8a7df0",
                ),
            ]
        )
        session.commit()
        yield session
    finally:
        session.close()


def test_monthly_summary_counts_pending_filters_hidden_removed(db_session: Session):
    summary = build_monthly_summary(db_session, month="2026-06")
    route_summary = asyncio.run(get_monthly_summary(month="2026-06", db=db_session))

    assert summary.month == "2026-06"
    # Pending "Shopping" $999 IS counted; hidden ($75) and removed ($50) are not.
    # June = Corner 120 + Cafe 100 (0.5 split) + Pending 999 = 1219.
    assert summary.total_spending == 1219.0
    assert summary.total_income == 3000.0
    assert summary.prev_month_spending == 80.0
    assert summary.spending_by_category[0].name == "GENERAL_MERCHANDISE"
    assert len(summary.recent_transactions) == 4

    assert route_summary.model_dump() == {
        "month": summary.month,
        "total_spending": summary.total_spending,
        "total_income": summary.total_income,
        "savings_rate": summary.savings_rate,
        "spending_by_category": [
            {"name": item.name, "value": item.value, "color": item.color}
            for item in summary.spending_by_category
        ],
        "recent_transactions": [
            {
                "id": item.id,
                "merchant": item.merchant,
                "account_name": item.account_name,
                "date": item.date,
                "category": item.category,
                "amount": item.amount,
                "initials": item.initials,
            }
            for item in summary.recent_transactions
        ],
        "prev_month_spending": summary.prev_month_spending,
    }


def test_get_spending_by_category_rolls_up_detailed_categories(db_session: Session):
    result = get_spending_by_category(
        db_session,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        top_n=10,
    )

    assert result.total_spending == 1219.0
    assert result.transaction_count == 3
    # Subcategory overrides (Dining Out) merge into FOOD_AND_DRINK — same as Cash Flow.
    assert [item.name for item in result.categories] == ["GENERAL_MERCHANDISE", "FOOD_AND_DRINK"]
    assert result.categories[0].transaction_count == 1
    assert result.categories[1].value == 220.0
    assert result.categories[1].transaction_count == 2


def test_search_transactions_filters_by_category_and_effective_amount(db_session: Session):
    result = search_transactions(
        db_session,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        category="dining",
        min_amount=90,
        limit=10,
    )

    assert result.total == 1
    assert result.returned == 1
    txn = result.transactions[0]
    assert txn.merchant == "Neighborhood Cafe"
    assert txn.amount == 100.0
    assert txn.rollup_category == "Dining Out"
    assert txn.direction == "spending"


def test_build_cash_flow_matches_expected_totals(db_session: Session):
    result = build_cash_flow(db_session, month="2026-06")

    assert result.month == "2026-06"
    assert result.total_income == 3000.0
    assert result.total_spending == 1219.0
    assert result.savings == 1781.0
    assert result.income_sources[0].label == "Paycheck"


def test_build_cash_flow_rolls_subcategory_into_primary(db_session: Session):
    """Manual 'Dining Out' / 'Restaurants' overrides merge into Food & Drink on cash flow."""
    card = db_session.query(Account).filter_by(plaid_account_id="acct_card").one()
    db_session.add(
        Transaction(
            account=card,
            merchant="Bistro",
            amount=Decimal("40.00"),
            date=date(2026, 6, 20),
            category_user="Restaurants",
            category_plaid="GENERAL_MERCHANDISE",
            pending=False,
            removed=False,
            hidden=False,
        )
    )
    db_session.commit()

    result = build_cash_flow(db_session, month="2026-06")
    by_id = {node.id: node for node in result.spending_categories}
    assert "Restaurants" not in by_id
    assert "Dining Out" not in by_id
    # Groceries (120) + Dining Out split (100) + Restaurants (40)
    assert by_id["FOOD_AND_DRINK"].amount == 260.0


def test_build_cash_flow_shows_investment_transfer_out(db_session: Session):
    """Investment funding must appear as Investments, not vanish into TRANSFER_OUT exclusion."""
    checking = db_session.query(Account).filter_by(plaid_account_id="acct_checking").one()
    db_session.add(
        Transaction(
            account=checking,
            merchant="Vanguard Contribution",
            amount=Decimal("500.00"),
            date=date(2026, 6, 15),
            category_plaid="TRANSFER_OUT",
            category_plaid_detailed="TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS",
            pending=False,
            removed=False,
            hidden=False,
        )
    )
    db_session.commit()

    result = build_cash_flow(db_session, month="2026-06")
    by_id = {node.id: node for node in result.spending_categories}
    assert "TRANSFER_OUT" not in by_id
    assert "Investments" not in by_id
    alloc = {node.id: node for node in result.allocation_nodes}
    assert alloc["Investments"].amount == 500.0
    assert result.total_spending == 1219.0
    assert result.savings == 3000.0 - 1219.0 - 500.0


def test_build_cash_flow_classifies_brokerage_ach_memo_as_investments(db_session: Session):
    """Bank memos like ACH→brokerage should count even when PFC is a generic transfer."""
    checking = db_session.query(Account).filter_by(plaid_account_id="acct_checking").one()
    db_session.add(
        Transaction(
            account=checking,
            merchant="Robinhood",
            amount=Decimal("250.00"),
            date=date(2026, 6, 16),
            category_plaid="TRANSFER_OUT",
            category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
            original_description="ACH deposit of $250 into Brokerage account ending in 4355",
            transaction_code="transfer",
            enrichment_json='{"payment_meta":{"payment_method":"ACH"},'
            '"counterparties":[{"name":"Robinhood","type":"financial_institution"}]}',
            pending=False,
            removed=False,
            hidden=False,
        )
    )
    db_session.commit()

    result = build_cash_flow(db_session, month="2026-06")
    alloc = {node.id: node for node in result.allocation_nodes}
    assert alloc["Investments"].amount == 250.0


def test_build_cash_flow_excludes_internal_transfer_in(db_session: Session):
    """Paycheck + internal savings transfer should not double-count income."""
    savings = Account(
        item=db_session.query(Item).filter_by(item_id="item_1").one(),
        plaid_account_id="acct_savings",
        name="Savings",
        type="depository",
        subtype="savings",
        current_balance=Decimal("5000.00"),
    )
    db_session.add(savings)
    db_session.flush()

    db_session.add_all(
        [
            Transaction(
                account=savings,
                merchant="Online Transfer",
                amount=Decimal("-3000.00"),
                date=date(2026, 6, 10),
                category_plaid="TRANSFER_IN",
                category_plaid_detailed="TRANSFER_IN_SAVINGS",
                pending=False,
                removed=False,
                hidden=False,
            ),
            Transaction(
                account=db_session.query(Account).filter_by(plaid_account_id="acct_checking").one(),
                merchant="Venmo",
                amount=Decimal("-50.00"),
                date=date(2026, 6, 12),
                category_plaid="TRANSFER_IN",
                category_plaid_detailed="TRANSFER_IN_OTHER_TRANSFER_IN",
                pending=False,
                removed=False,
                hidden=False,
            ),
        ]
    )
    db_session.commit()

    result = build_cash_flow(db_session, month="2026-06")

    # Paycheck ($3000) + Venmo P2P ($50); internal savings transfer excluded
    assert result.total_income == 3050.0
    income_by_label = {node.label: node.amount for node in result.income_sources}
    assert income_by_label.get("Paycheck") == 3000.0
    assert income_by_label.get("TRANSFER_IN") == 50.0


def test_cash_flow_sankey_data_returns_mermaid_links(
    db_session: Session, budgets_session: Session, monkeypatch: pytest.MonkeyPatch
):
    @contextmanager
    def fake_ledger_session():
        yield db_session

    @contextmanager
    def fake_budgets_session():
        yield budgets_session

    monkeypatch.setattr(mcp_server_module, "ledger_session", fake_ledger_session)
    monkeypatch.setattr(mcp_server_module, "budgets_session", fake_budgets_session)

    result = mcp_server_module.get_cash_flow_sankey_data("2026-06")

    assert result.month == "2026-06"
    assert result.total_income == 3000.0
    assert result.mermaid.startswith("sankey-beta")
    assert "Paycheck,Income pool,3000" in result.mermaid
    assert any(link.target == "Unallocated" for link in result.sankey_links)
    assert "<svg" in result.svg
    assert "INCOME" in result.svg


def test_build_cash_flow_sankey_svg_fits_tunnel_when_spending_exceeds_income():
    from app.services.analytics_service import CashFlowData, CashFlowNodeItem
    from mcp_server.sankey import _build_layout

    flow = CashFlowData(
        month="2026-07",
        total_income=500.0,
        total_spending=1200.0,
        savings=0.0,
        income_sources=[
            CashFlowNodeItem(
                id="paycheck",
                label="Paycheck",
                amount=500.0,
                color="#4ec38a",
                top_transactions=[],
            )
        ],
        spending_categories=[
            CashFlowNodeItem(
                id="rent",
                label="RENT_AND_UTILITIES",
                amount=700.0,
                color="#5b8def",
                top_transactions=[],
            ),
            CashFlowNodeItem(
                id="food",
                label="FOOD_AND_DRINK",
                amount=500.0,
                color="#e8a838",
                top_transactions=[],
            ),
        ],
    )

    layout = _build_layout(flow)
    assert layout is not None

    right_band_total = sum(node.h for node in layout.right_nodes) + max(
        0, len(layout.right_nodes) - 1
    ) * 8
    right_ribbon_total = sum(link.ty1 - link.ty0 for link in layout.right_links) + max(
        0, len(layout.right_links) - 1
    ) * 8

    assert right_band_total <= layout.tunnel_h + 1
    assert right_ribbon_total <= layout.tunnel_h + 1


def test_build_cash_flow_sankey_svg_renders_income_tunnel_and_savings(db_session: Session):
    flow = build_cash_flow(db_session, month="2026-06")
    svg = build_cash_flow_sankey_svg(flow)

    assert "<svg" in svg
    assert "Paycheck" in svg
    assert "Unallocated" in svg
    assert 'fill="url(#tg)"' in svg
    assert "Flow width represents relative amount" not in svg
    assert 'width="100%"' in svg


def test_build_cash_flow_sankey_svg_escapes_commas_in_labels():
    from app.services.analytics_service import CashFlowData, CashFlowNodeItem

    flow = CashFlowData(
        month="2026-06",
        total_income=100.0,
        total_spending=100.0,
        savings=0.0,
        income_sources=[
            CashFlowNodeItem(
                id="income_1",
                label="Side gig, LLC",
                amount=100.0,
                color="#4ec38a",
                top_transactions=[],
            )
        ],
        spending_categories=[
            CashFlowNodeItem(
                id="spend_1",
                label="Dining Out",
                amount=100.0,
                color="#5b8def",
                top_transactions=[],
            )
        ],
    )

    svg = build_cash_flow_sankey_svg(flow)

    assert "Side Gig" in svg


def test_build_recurring_spend_detects_series(db_session: Session):
    result = build_recurring_spend(db_session, months=12)

    assert result.subscriptions
    netflix = result.subscriptions[0]
    assert netflix.merchant == "Netflix 9012"
    assert netflix.average_amount == 15.0
    assert netflix.cadence == "monthly"


def test_build_budget_vs_actual_combines_budgets_and_ledger(db_session: Session, budgets_session: Session):
    result = build_budget_vs_actual(db_session, budgets_session, month="2026-06")

    assert result.month == "2026-06"
    assert result.total_limit == 240.0
    # Dining Out $100 (tracked) + Groceries $120 + pending Shopping $999 → Misc.
    assert result.total_spent == 1219.0
    misc = next(item for item in result.budgets if item.virtual)
    assert misc.category == "Misc."
    assert misc.spent == 1119.0
    assert misc.over_budget is False
    assert any(item.over_budget for item in result.budgets if not item.virtual)


def test_build_investment_performance_returns_portfolio_metrics(db_session: Session):
    result = build_investment_performance(db_session, months=24, top_positions=5)

    assert result.total_value == 1200.0
    assert result.total_cost_basis == 1000.0
    assert result.unrealized_gain == 200.0
    assert result.account_count == 1
    assert result.position_count == 1
    assert result.top_positions[0].ticker == "VTI"
    assert result.history[-1].total == 1200.0


def test_build_investment_performance_scales_holdings_for_margin(tmp_path):
    """Gross holdings can exceed net equity when margin is in use."""
    from decimal import Decimal

    db_path = tmp_path / "margin-ledger.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()

    user = User(id=1, username="default_user")
    item = Item(
        user=user,
        item_id="margin_item",
        institution_name="Brokerage",
        access_token_encrypted="encrypted-margin",
    )
    account = Account(
        item=item,
        plaid_account_id="acct_margin",
        name="Margin Brokerage",
        type="investment",
        subtype="brokerage",
        current_balance=Decimal("2800.00"),
    )
    session.add_all([user, item, account])
    session.flush()

    securities = [
        Security(plaid_security_id="sec_voo", ticker_symbol="VOO", name="VOO", type="etf"),
        Security(plaid_security_id="sec_cash", ticker_symbol="CUR:USD", name="Cash", type="cash"),
    ]
    session.add_all(securities)
    session.flush()

    session.add_all([
        Holding(
            account=account,
            security=securities[0],
            quantity=Decimal("4"),
            institution_value=Decimal("3085.00"),
            cost_basis=Decimal("2500.00"),
        ),
        Holding(
            account=account,
            security=securities[1],
            quantity=Decimal("1928"),
            institution_value=Decimal("1928.00"),
        ),
    ])
    session.commit()

    result = build_investment_performance(session, months=6, top_positions=5)

    assert result.total_value == 2800.0
    assert sum(slice.value for slice in result.allocation) == pytest.approx(2800.0, abs=0.01)
    assert result.top_positions[0].ticker == "VOO"
    assert result.top_positions[0].value == pytest.approx(1723.12, abs=0.01)
    assert result.top_positions[1].ticker == "CUR:USD"
    assert result.top_positions[1].value == pytest.approx(1076.88, abs=0.01)

    session.close()


def test_build_net_worth_uses_live_balances_and_snapshots(db_session: Session):
    result = build_net_worth(db_session, months=24)

    assert result.current_net_worth == 3200.0
    assert result.total_assets == 3700.0
    assert result.total_liabilities == 500.0
    assert result.snapshots
    assert result.snapshots[-1].total == 3200.0
    assert any(item.name == "Checking" for item in result.accounts)


def test_chart_cash_flow_returns_inline_svg_image(
    db_session: Session, budgets_session: Session, monkeypatch: pytest.MonkeyPatch
):
    @contextmanager
    def fake_ledger_session():
        yield db_session

    @contextmanager
    def fake_budgets_session():
        yield budgets_session

    monkeypatch.setattr(mcp_server_module, "ledger_session", fake_ledger_session)
    monkeypatch.setattr(mcp_server_module, "budgets_session", fake_budgets_session)

    async def _check() -> None:
        tool = await mcp_server_module.mcp.get_tool("chart_cash_flow")
        assert (tool.meta or {}).get("ui") is None
        result = await mcp_server_module.mcp.call_tool("chart_cash_flow", {"month": "2026-06"})
        assert result.structured_content is not None
        assert result.structured_content["month"] == "2026-06"
        image_blocks = [block for block in result.content if getattr(block, "type", None) == "image"]
        assert len(image_blocks) == 1
        assert image_blocks[0].mimeType == "image/svg"
        assert "[Rendered Prefab UI]" not in str(result.content)

    asyncio.run(_check())


def test_chart_tools_are_not_embed_widgets():
    async def _check() -> None:
        for name in ("chart_cash_flow", "chart_sankey"):
            tool = await mcp_server_module.mcp.get_tool(name)
            meta = tool.meta or {}
            assert "ui" not in meta, f"{name} must not be a Prefab embed widget"

    asyncio.run(_check())


def test_database_diagnostics_reports_active_paths_and_counts(
    db_session: Session,
    budgets_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    @contextmanager
    def fake_ledger_session():
        yield db_session

    @contextmanager
    def fake_budgets_session():
        yield budgets_session

    monkeypatch.setattr(mcp_server_module, "ledger_session", fake_ledger_session)
    monkeypatch.setattr(mcp_server_module, "budgets_session", fake_budgets_session)
    monkeypatch.setattr(mcp_server_module, "ledger_database_path", lambda: "X:/tmp/test-ledger.db")
    monkeypatch.setattr(mcp_server_module, "budgets_database_path", lambda: "X:/tmp/test-budgets.db")

    result = mcp_server_module.get_database_diagnostics("2026-06")

    assert result.month == "2026-06"
    assert result.ledger_database_path == "X:/tmp/test-ledger.db"
    assert result.budgets_database_path == "X:/tmp/test-budgets.db"
    assert result.total_transactions == 10
    assert result.visible_transactions == 7
    assert result.visible_transactions_in_month == 3
    assert result.latest_transaction_date == "2026-06-13"
    assert result.budgets_in_month == 2
    assert result.latest_budget_month == "2026-06"
