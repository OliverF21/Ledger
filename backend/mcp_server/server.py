"""
Local MCP server that exposes read-only spending analysis tools.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from sqlalchemy import func
from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult
from pydantic import Field

from app.budgets_db import Budget
from app.models import Transaction
from app.services.analytics_service import (
    build_budget_vs_actual,
    build_cash_flow,
    build_monthly_summary,
    build_net_worth,
    build_recurring_spend,
    build_trends,
    get_spending_by_category as get_spending_by_category_data,
    search_transactions as search_transaction_data,
)
from app.services.investment_service import build_investment_performance
from app.services.optimization_service import build_optimization_suggestion
from mcp_server.proposals import create_budget_proposal
from mcp_server.sankey import build_cash_flow_sankey_payload, build_cash_flow_sankey_svg
from mcp_server.visuals import cash_flow_chart_result
from mcp_server.db import (
    budgets_database_path,
    budgets_session,
    ledger_database_path,
    ledger_session,
)
from mcp_server.schemas import (
    BudgetVsActualItemResult,
    BudgetVsActualResult,
    CashFlowNodeResult,
    CashFlowResult,
    CashFlowSankeyResult,
    CashFlowTransactionResult,
    CategorySpendResult,
    DatabaseDiagnosticsResult,
    InvestmentAllocationResult,
    InvestmentHistoryPointResult,
    InvestmentPerformanceResult,
    InvestmentPositionResult,
    MonthlySpendingResult,
    ObjectiveResult,
    PortfolioOptimizationResult,
    RecentTransactionResult,
    ProposalResult,
    RecurringSpendItemResult,
    RecurringSpendResult,
    SankeyLinkResult,
    SpendingByCategoryResult,
    TransactionRecord,
    TransactionSearchResult,
)

mcp = FastMCP(
    "Ledger",
    instructions=(
        "Read-only personal finance analytics from the local OpenTrack SQLite ledger "
        "(ledger.db). Tools query transactions and balances via SQLAlchemy using the same "
        "rules as the web app: exclude removed/pending/hidden rows, apply user_split_pct, "
        "and roll up categories consistently.\n\n"
        "Data tools (return JSON — Claude summarizes and draws charts in chat):\n"
        "- cash_flow_sankey_data — cash-flow Sankey link rows + totals from ledger.db\n"
        "- cash_flow_summary — income/spending buckets as JSON\n"
        "- monthly_spending_summary — monthly KPIs and category breakdown\n"
        "- spending_by_category — category totals for a date range\n"
        "- budget_status — budget vs actual\n"
        "- recurring_subscriptions — recurring charges\n"
        "- investment_performance — portfolio metrics\n"
        "- portfolio_optimization — suggested allocation (Max Sharpe + Max Quadratic "
        "Utility + efficient frontier); empty unless the user has advanced optimization "
        "enabled in Settings\n"
        "- transaction_search — evidence rows\n"
        "- net_worth_data — net worth history and account breakdown (JSON)\n"
        "- trends_data — monthly spending vs income series (JSON)\n\n"
        "Visual chart tools (return inline SVG images — no embed widgets):\n"
        "- chart_cash_flow / chart_sankey — ALWAYS use for cash-flow Sankey diagrams; "
        "they match the Ledger Cash Flow page. Do not redraw Mermaid from cash_flow_sankey_data.\n\n"
        "Advisor / write-intent tool (you CANNOT change the user's data):\n"
        "- propose_budget — stage a budget suggestion for the user to review and apply "
        "inside Ledger. You do not apply it; you cannot. After analyzing spending, if you "
        "recommend a budget change, call propose_budget, then tell the user to open the "
        "returned apply_url (Ledger's Advisor page) to apply it. Requires the Ledger "
        "backend to be running."
    ),
)


def _cash_flow_node_result(node) -> CashFlowNodeResult:
    return CashFlowNodeResult(
        id=node.id,
        label=node.label,
        amount=node.amount,
        color=node.color,
        top_transactions=[
            CashFlowTransactionResult(
                merchant=txn.merchant,
                amount=txn.amount,
                date=txn.date,
            )
            for txn in node.top_transactions
        ],
    )


def _build_cash_flow_sankey_result(month: str | None) -> CashFlowSankeyResult:
    with ledger_session() as db:
        flow = build_cash_flow(db, month=month)

    payload = build_cash_flow_sankey_payload(flow)
    svg = build_cash_flow_sankey_svg(flow)

    return CashFlowSankeyResult(
        month=payload.month,
        total_income=payload.total_income,
        total_spending=payload.total_spending,
        savings=payload.savings,
        spending_pct=payload.spending_pct,
        savings_pct=payload.savings_pct,
        income_sources=[_cash_flow_node_result(node) for node in payload.income_sources],
        uses=[_cash_flow_node_result(node) for node in payload.uses],
        sankey_links=[
            SankeyLinkResult(source=link.source, target=link.target, value=link.value)
            for link in payload.sankey_links
        ],
        svg=svg,
        mermaid=payload.mermaid,
    )


@mcp.tool(
    name="cash_flow_sankey_data",
    tags={"analytics", "cashflow", "sankey"},
    description=(
        "Cash-flow Sankey data from ledger.db. Returns totals, link rows, and SVG markup. "
        "For the visual diagram, use chart_cash_flow instead."
    ),
)
def get_cash_flow_sankey_data(
    month: Annotated[
        str | None,
        Field(description="Calendar month in YYYY-MM format. Defaults to the current month."),
    ] = None,
) -> CashFlowSankeyResult:
    """Cash-flow Sankey data (JSON). Use chart_cash_flow for the inline SVG chart."""
    return _build_cash_flow_sankey_result(month)


def _build_cash_flow_chart(month: str | None) -> ToolResult:
    with ledger_session() as db:
        flow = build_cash_flow(db, month=month)
    svg = build_cash_flow_sankey_svg(flow)
    return cash_flow_chart_result(flow, svg)


@mcp.tool(
    name="chart_cash_flow",
    tags={"analytics", "visualization", "cashflow", "sankey"},
    description="Cash-flow ribbon Sankey as an inline SVG image (no embed widget).",
)
def chart_cash_flow(
    month: Annotated[
        str | None,
        Field(description="Calendar month in YYYY-MM format. Defaults to the current month."),
    ] = None,
) -> ToolResult:
    """Show the cash-flow Sankey ribbon diagram as an inline image."""
    return _build_cash_flow_chart(month)


@mcp.tool(
    name="chart_sankey",
    tags={"analytics", "visualization", "cashflow", "sankey"},
    description="Alias of chart_cash_flow — inline SVG Sankey diagram.",
)
def chart_sankey(
    month: Annotated[
        str | None,
        Field(description="Calendar month in YYYY-MM format. Defaults to the current month."),
    ] = None,
) -> ToolResult:
    """Alias for chart_cash_flow."""
    return _build_cash_flow_chart(month)


@mcp.tool(name="net_worth_data", tags={"analytics", "net-worth"})
def get_net_worth_data(
    months: Annotated[
        int,
        Field(description="Trailing months of net-worth history.", ge=1, le=24),
    ] = 6,
) -> dict:
    """Return net worth history, account breakdown, and change metrics as JSON."""
    with ledger_session() as db:
        data = build_net_worth(db, months=months)
    return {
        "current_net_worth": data.current_net_worth,
        "total_assets": data.total_assets,
        "total_liabilities": data.total_liabilities,
        "change_amount": data.change_amount,
        "change_pct": data.change_pct,
        "snapshots": [{"date": point.date, "total": point.total} for point in data.snapshots],
        "accounts": [
            {
                "id": account.id,
                "name": account.name,
                "type": account.type,
                "subtype": account.subtype,
                "balance": account.balance,
                "is_liability": account.is_liability,
            }
            for account in data.accounts
        ],
    }


@mcp.tool(name="trends_data", tags={"analytics", "trends"})
def get_trends_data(
    months: Annotated[
        int,
        Field(description="Number of months in the trend window.", ge=3, le=24),
    ] = 6,
) -> dict:
    """Return monthly spending vs income trends as JSON."""
    with ledger_session() as db:
        trends = build_trends(db, months=months)
    return {
        "period_spending": trends.period_spending,
        "period_income": trends.period_income,
        "monthly_avg_spending": trends.monthly_avg_spending,
        "prev_monthly_avg_spending": trends.prev_monthly_avg_spending,
        "spending_change_pct": trends.spending_change_pct,
        "months": [
            {
                "label": month.label,
                "full_label": month.full_label,
                "total_spending": month.total_spending,
                "total_income": month.total_income,
                "is_partial": month.is_partial,
            }
            for month in trends.months
        ],
        "categories": [
            {
                "name": category.name,
                "total": category.total,
                "last_full": category.last_full,
                "prior_avg": category.prior_avg,
                "change_vs_prior_pct": category.change_vs_prior_pct,
            }
            for category in trends.categories
        ],
    }


@mcp.tool(name="monthly_spending_summary", tags={"analytics", "spending"})
def get_monthly_spending(
    month: Annotated[
        str | None,
        Field(description="Calendar month in YYYY-MM format. Defaults to the current month."),
    ] = None,
) -> MonthlySpendingResult:
    """Return the monthly spending, income, savings rate, and recent evidence rows."""
    with ledger_session() as db:
        summary = build_monthly_summary(db, month=month)

    return MonthlySpendingResult(
        month=summary.month,
        total_spending=summary.total_spending,
        total_income=summary.total_income,
        savings_rate=summary.savings_rate,
        prev_month_spending=summary.prev_month_spending,
        spending_by_category=[
            CategorySpendResult(
                name=item.name,
                value=item.value,
                color=item.color,
                transaction_count=item.transaction_count,
            )
            for item in summary.spending_by_category
        ],
        recent_transactions=[
            RecentTransactionResult(
                id=item.id,
                merchant=item.merchant,
                account_name=item.account_name,
                date=item.date,
                category=item.category,
                amount=item.amount,
                initials=item.initials,
            )
            for item in summary.recent_transactions
        ],
    )


@mcp.tool(name="spending_by_category", tags={"analytics", "spending"})
def get_spending_by_category(
    start_date: Annotated[
        str,
        Field(description="Inclusive start date in YYYY-MM-DD format."),
    ],
    end_date: Annotated[
        str,
        Field(description="Inclusive end date in YYYY-MM-DD format."),
    ],
    top_n: Annotated[
        int,
        Field(description="Maximum number of categories to return.", ge=1, le=50),
    ] = 10,
) -> SpendingByCategoryResult:
    """Return category totals for a date window using the app's exclusion and split rules."""
    with ledger_session() as db:
        result = get_spending_by_category_data(
            db,
            start_date=_parse_iso_date(start_date, field_name="start_date"),
            end_date=_parse_iso_date(end_date, field_name="end_date"),
            top_n=top_n,
        )

    return SpendingByCategoryResult(
        start_date=result.start_date,
        end_date=result.end_date,
        total_spending=result.total_spending,
        transaction_count=result.transaction_count,
        categories=[
            CategorySpendResult(
                name=item.name,
                value=item.value,
                color=item.color,
                transaction_count=item.transaction_count,
            )
            for item in result.categories
        ],
    )


@mcp.tool(name="cash_flow_summary", tags={"analytics", "cashflow"})
def get_cash_flow(
    month: Annotated[
        str | None,
        Field(description="Calendar month in YYYY-MM format. Defaults to the current month."),
    ] = None,
) -> CashFlowResult:
    """Return income sources, spending buckets, and savings for a month (JSON only). For Sankey diagrams use cash_flow_sankey_data instead."""
    with ledger_session() as db:
        result = build_cash_flow(db, month=month)

    return CashFlowResult(
        month=result.month,
        total_income=result.total_income,
        total_spending=result.total_spending,
        savings=result.savings,
        income_sources=[
            CashFlowNodeResult(
                id=node.id,
                label=node.label,
                amount=node.amount,
                color=node.color,
                top_transactions=[
                    CashFlowTransactionResult(
                        merchant=txn.merchant,
                        amount=txn.amount,
                        date=txn.date,
                    )
                    for txn in node.top_transactions
                ],
            )
            for node in result.income_sources
        ],
        spending_categories=[
            CashFlowNodeResult(
                id=node.id,
                label=node.label,
                amount=node.amount,
                color=node.color,
                top_transactions=[
                    CashFlowTransactionResult(
                        merchant=txn.merchant,
                        amount=txn.amount,
                        date=txn.date,
                    )
                    for txn in node.top_transactions
                ],
            )
            for node in result.spending_categories
        ],
    )


@mcp.tool(name="recurring_subscriptions", tags={"analytics", "subscriptions"})
def get_recurring_spend(
    months: Annotated[
        int,
        Field(description="Trailing months of history to inspect for recurring spend.", ge=3, le=24),
    ] = 12,
) -> RecurringSpendResult:
    """Return likely recurring subscriptions and repeated merchant charges."""
    with ledger_session() as db:
        result = build_recurring_spend(db, months=months)

    return RecurringSpendResult(
        months=result.months,
        subscriptions=[
            RecurringSpendItemResult(
                merchant=item.merchant,
                category=item.category,
                cadence=item.cadence,
                average_amount=item.average_amount,
                last_date=item.last_date,
                next_expected_date=item.next_expected_date,
                occurrence_count=item.occurrence_count,
            )
            for item in result.subscriptions
        ],
    )


@mcp.tool(name="budget_status", tags={"analytics", "budgets"})
def get_budget_vs_actual(
    month: Annotated[
        str | None,
        Field(description="Calendar month in YYYY-MM format. Defaults to the current month."),
    ] = None,
) -> BudgetVsActualResult:
    """Return monthly budget limits versus actual spending."""
    with ledger_session() as ledger_db, budgets_session() as budget_db:
        result = build_budget_vs_actual(ledger_db, budget_db, month=month)

    return BudgetVsActualResult(
        month=result.month,
        total_limit=result.total_limit,
        total_spent=result.total_spent,
        total_remaining=result.total_remaining,
        budgets=[
            BudgetVsActualItemResult(
                id=item.id,
                category=item.category,
                limit=item.limit,
                spent=item.spent,
                remaining=item.remaining,
                percent_used=item.percent_used,
                over_budget=item.over_budget,
                color=item.color,
            )
            for item in result.budgets
        ],
    )


@mcp.tool(name="database_diagnostics", tags={"analytics", "diagnostics"})
def get_database_diagnostics(
    month: Annotated[
        str | None,
        Field(description="Calendar month in YYYY-MM format. Defaults to the current month."),
    ] = None,
) -> DatabaseDiagnosticsResult:
    """Return the active database paths and basic row counts for debugging MCP data access."""
    year, mon, start, end, month_key = _resolve_month_window(month)

    with ledger_session() as ledger_db:
        total_transactions = ledger_db.query(func.count(Transaction.id)).scalar() or 0
        visible_transactions = (
            ledger_db.query(func.count(Transaction.id))
            .filter(
                Transaction.removed.is_(False),
                Transaction.pending.is_(False),
                Transaction.hidden.is_(False),
            )
            .scalar()
            or 0
        )
        visible_transactions_in_month = (
            ledger_db.query(func.count(Transaction.id))
            .filter(
                Transaction.removed.is_(False),
                Transaction.pending.is_(False),
                Transaction.hidden.is_(False),
                Transaction.date >= start,
                Transaction.date < end,
            )
            .scalar()
            or 0
        )
        latest_transaction_date = ledger_db.query(func.max(Transaction.date)).scalar()

    with budgets_session() as budget_db:
        budgets_in_month = budget_db.query(func.count(Budget.id)).filter(Budget.month == month_key).scalar() or 0
        latest_budget_month = budget_db.query(func.max(Budget.month)).scalar()

    return DatabaseDiagnosticsResult(
        ledger_database_path=ledger_database_path(),
        budgets_database_path=budgets_database_path(),
        month=month_key,
        total_transactions=int(total_transactions),
        visible_transactions=int(visible_transactions),
        visible_transactions_in_month=int(visible_transactions_in_month),
        latest_transaction_date=latest_transaction_date.isoformat() if latest_transaction_date else None,
        budgets_in_month=int(budgets_in_month),
        latest_budget_month=latest_budget_month,
    )


@mcp.tool(name="transaction_search", tags={"analytics", "transactions"})
def search_transactions(
    start_date: Annotated[
        str | None,
        Field(description="Optional inclusive start date in YYYY-MM-DD format."),
    ] = None,
    end_date: Annotated[
        str | None,
        Field(description="Optional inclusive end date in YYYY-MM-DD format."),
    ] = None,
    merchant: Annotated[
        str | None,
        Field(description="Optional case-insensitive merchant substring filter."),
    ] = None,
    category: Annotated[
        str | None,
        Field(description="Optional category substring filter across user, Plaid, and rollup categories."),
    ] = None,
    account: Annotated[
        str | None,
        Field(description="Optional case-insensitive account name substring filter."),
    ] = None,
    min_amount: Annotated[
        float | None,
        Field(description="Optional minimum absolute effective amount."),
    ] = None,
    max_amount: Annotated[
        float | None,
        Field(description="Optional maximum absolute effective amount."),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of transaction rows to return.", ge=1, le=100),
    ] = 25,
) -> TransactionSearchResult:
    """Return matching transaction rows for evidence-backed analysis."""
    parsed_start = _parse_optional_iso_date(start_date, field_name="start_date")
    parsed_end = _parse_optional_iso_date(end_date, field_name="end_date")

    with ledger_session() as db:
        result = search_transaction_data(
            db,
            start_date=parsed_start,
            end_date=parsed_end,
            merchant=_clean_optional_text(merchant),
            category=_clean_optional_text(category),
            account=_clean_optional_text(account),
            min_amount=min_amount,
            max_amount=max_amount,
            limit=limit,
        )

    return TransactionSearchResult(
        total=result.total,
        returned=result.returned,
        filters={
            key: value
            for key, value in {
                "start_date": start_date,
                "end_date": end_date,
                "merchant": _clean_optional_text(merchant),
                "category": _clean_optional_text(category),
                "account": _clean_optional_text(account),
                "min_amount": min_amount,
                "max_amount": max_amount,
                "limit": limit,
            }.items()
            if value is not None
        },
        transactions=[
            TransactionRecord(
                id=item.id,
                date=item.date,
                merchant=item.merchant,
                amount=item.amount,
                original_amount=item.original_amount,
                direction=item.direction,
                category=item.category,
                rollup_category=item.rollup_category,
                category_user=item.category_user,
                category_plaid=item.category_plaid,
                category_plaid_detailed=item.category_plaid_detailed,
                account_name=item.account_name,
                account_type=item.account_type,
                account_subtype=item.account_subtype,
                payment_channel=item.payment_channel,
                user_split_pct=item.user_split_pct,
                manual_override=item.manual_override,
                notes=item.notes,
                enrichment=item.enrichment,
            )
            for item in result.transactions
        ],
    )


@mcp.tool(name="investment_performance", tags={"analytics", "investments"})
def get_investment_performance(
    months: Annotated[
        int,
        Field(description="Trailing months of balance history to include.", ge=1, le=24),
    ] = 6,
    top_positions: Annotated[
        int,
        Field(description="Maximum number of largest positions to return.", ge=1, le=25),
    ] = 10,
) -> InvestmentPerformanceResult:
    """Return portfolio performance, allocation, history, and largest positions."""
    with ledger_session() as db:
        result = build_investment_performance(db, months=months, top_positions=top_positions)

    return InvestmentPerformanceResult(
        months=result.months,
        total_value=result.total_value,
        total_cost_basis=result.total_cost_basis,
        unrealized_gain=result.unrealized_gain,
        account_count=result.account_count,
        position_count=result.position_count,
        last_synced_at=result.last_synced_at,
        change_amount=result.change_amount,
        change_pct=result.change_pct,
        allocation=[
            InvestmentAllocationResult(
                type=item.type,
                value=item.value,
                pct=item.pct,
                color=item.color,
            )
            for item in result.allocation
        ],
        top_positions=[
            InvestmentPositionResult(
                account_name=item.account_name,
                ticker=item.ticker,
                name=item.name,
                type=item.type,
                quantity=item.quantity,
                price=item.price,
                value=item.value,
                cost_basis=item.cost_basis,
                gain=item.gain,
                gain_pct=item.gain_pct,
                currency=item.currency,
            )
            for item in result.top_positions
        ],
        history=[
            InvestmentHistoryPointResult(date=item.date, total=item.total)
            for item in result.history
        ],
    )


@mcp.tool(name="portfolio_optimization", tags={"analytics", "investments"})
def portfolio_optimization() -> PortfolioOptimizationResult:
    """Suggested portfolio allocation (Max Sharpe, Max Quadratic Utility, and
    an efficient frontier), computed from the user's current holdings and
    preferences. Returns empty objectives/advanced_enabled=False unless the
    user has advanced optimization enabled in Settings -- there is no
    separate, always-on basic engine. Read-only -- structured metrics only,
    no generated explanation; summarize/explain the numbers yourself."""
    with ledger_session() as db:
        data = build_optimization_suggestion(db)
        return PortfolioOptimizationResult(
            advanced_enabled=data.advanced_enabled,
            position_cap_pct=data.position_cap_pct,
            objectives=[
                ObjectiveResult(
                    name=o.name, tickers=[vars(t) for t in o.tickers],
                    expected_return_pct=o.expected_return_pct, volatility_pct=o.volatility_pct, sharpe=o.sharpe,
                )
                for o in data.objectives
            ],
            frontier_points=data.frontier_points,
            sector_breakdown=data.sector_breakdown,
            clip_log=data.clip_log,
            data_points=data.data_points,
            insufficient_data=data.insufficient_data,
        )


def _resolve_month_window(month: str | None) -> tuple[int, int, date, date, str]:
    if month:
        try:
            year_str, month_str = month.split("-", maxsplit=1)
            year = int(year_str)
            mon = int(month_str)
        except ValueError as exc:
            raise ValueError("month must be in YYYY-MM format") from exc
        if mon < 1 or mon > 12:
            raise ValueError("month must be in YYYY-MM format")
        anchor = date(year, mon, 1)
    else:
        anchor = date.today()

    start = anchor.replace(day=1)
    if anchor.month == 12:
        end = date(anchor.year + 1, 1, 1)
    else:
        end = date(anchor.year, anchor.month + 1, 1)
    return anchor.year, anchor.month, start, end, f"{anchor.year:04d}-{anchor.month:02d}"


def _parse_iso_date(value: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format") from exc


def _parse_optional_iso_date(value: str | None, *, field_name: str) -> date | None:
    if value is None:
        return None
    return _parse_iso_date(value, field_name=field_name)


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@mcp.tool(
    name="propose_budget",
    tags={"advisor", "budgets", "write-intent"},
    description=(
        "Stage a budget suggestion for the user to review and APPLY inside Ledger. This "
        "does NOT change any data — it creates a pending proposal the user applies from "
        "Ledger's Advisor page (you cannot apply it). Use after analyzing spending when you "
        "recommend setting or changing a monthly budget. Requires the Ledger backend to be "
        "running; returns an apply_url to send the user to."
    ),
)
def propose_budget(
    category_name: Annotated[
        str,
        Field(description="Display label for the budget, e.g. 'Food & Drink'."),
    ],
    limit: Annotated[
        float,
        Field(description="Proposed monthly limit in dollars (must be > 0).", gt=0),
    ],
    month: Annotated[
        str | None,
        Field(description="Target month YYYY-MM. Defaults to the current month."),
    ] = None,
    category_key: Annotated[
        str | None,
        Field(
            description=(
                "Optional Plaid PFC parent key (e.g. FOOD_AND_DRINK, TRANSPORTATION) so the "
                "budget aggregates spending correctly. Omit to match by display name."
            )
        ),
    ] = None,
    rationale: Annotated[
        str | None,
        Field(description="Short explanation shown to the user for why you suggest this limit."),
    ] = None,
) -> ProposalResult:
    """Stage a set_budget proposal in Ledger for the user to apply."""
    return create_budget_proposal(
        category_name=category_name,
        limit=limit,
        month=month,
        category_key=category_key,
        rationale=rationale,
    )


if __name__ == "__main__":
    mcp.run()
