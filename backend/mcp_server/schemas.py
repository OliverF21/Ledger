"""
Pydantic schemas exposed by the analytics MCP server.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CategorySpendResult(BaseModel):
    name: str
    value: float
    color: str
    transaction_count: int = Field(description="How many transactions contributed to this category total")


class RecentTransactionResult(BaseModel):
    id: int
    merchant: str
    account_name: str | None = None
    date: str
    category: str | None = None
    amount: float
    initials: str


class MonthlySpendingResult(BaseModel):
    month: str
    total_spending: float
    total_income: float
    savings_rate: float
    prev_month_spending: float
    spending_by_category: list[CategorySpendResult]
    recent_transactions: list[RecentTransactionResult]


class SpendingByCategoryResult(BaseModel):
    start_date: str
    end_date: str
    total_spending: float
    transaction_count: int
    categories: list[CategorySpendResult]


class TransactionRecord(BaseModel):
    id: int
    date: str
    merchant: str
    amount: float
    original_amount: float
    direction: str
    category: str | None = None
    rollup_category: str
    category_user: str | None = None
    category_plaid: str | None = None
    category_plaid_detailed: str | None = None
    account_name: str | None = None
    account_type: str | None = None
    account_subtype: str | None = None
    payment_channel: str | None = None
    user_split_pct: float | None = None
    manual_override: bool
    notes: str | None = None
    enrichment: dict[str, Any] | None = None


class TransactionSearchResult(BaseModel):
    total: int
    returned: int
    transactions: list[TransactionRecord]
    filters: dict[str, Any]


class CashFlowTransactionResult(BaseModel):
    merchant: str
    amount: float
    date: str


class CashFlowNodeResult(BaseModel):
    id: str
    label: str
    amount: float
    color: str
    top_transactions: list[CashFlowTransactionResult]


class CashFlowResult(BaseModel):
    month: str
    total_income: float
    total_spending: float
    savings: float
    income_sources: list[CashFlowNodeResult]
    spending_categories: list[CashFlowNodeResult]


class SankeyLinkResult(BaseModel):
    source: str
    target: str
    value: float


class CashFlowSankeyResult(BaseModel):
    month: str
    total_income: float
    total_spending: float
    savings: float
    spending_pct: float
    savings_pct: float
    income_sources: list[CashFlowNodeResult]
    uses: list[CashFlowNodeResult]
    sankey_links: list[SankeyLinkResult]
    svg: str = Field(description="Ribbon Sankey SVG matching the OpenTrack Cash Flow page.")
    mermaid: str = Field(description="Mermaid sankey-beta source (for debugging; prefer chart_cash_flow image).")


class RecurringSpendItemResult(BaseModel):
    merchant: str
    category: str
    cadence: str
    average_amount: float
    last_date: str
    next_expected_date: str
    occurrence_count: int


class RecurringSpendResult(BaseModel):
    months: int
    subscriptions: list[RecurringSpendItemResult]


class BudgetVsActualItemResult(BaseModel):
    id: int
    category: str
    limit: float
    spent: float
    remaining: float
    percent_used: float
    over_budget: bool
    color: str
    virtual: bool = False


class BudgetVsActualResult(BaseModel):
    month: str
    budgets: list[BudgetVsActualItemResult]
    total_limit: float
    total_spent: float
    total_remaining: float


class DatabaseDiagnosticsResult(BaseModel):
    ledger_database_path: str | None = None
    budgets_database_path: str | None = None
    month: str
    total_transactions: int
    visible_transactions: int
    visible_transactions_in_month: int
    latest_transaction_date: str | None = None
    budgets_in_month: int
    latest_budget_month: str | None = None


class InvestmentAllocationResult(BaseModel):
    type: str
    value: float
    pct: float
    color: str


class InvestmentPositionResult(BaseModel):
    account_name: str
    ticker: str | None = None
    name: str | None = None
    type: str | None = None
    quantity: float
    price: float | None = None
    value: float
    cost_basis: float | None = None
    gain: float | None = None
    gain_pct: float | None = None
    currency: str | None = None


class InvestmentHistoryPointResult(BaseModel):
    date: str
    total: float


class InvestmentPerformanceResult(BaseModel):
    months: int
    total_value: float
    total_cost_basis: float | None = None
    unrealized_gain: float | None = None
    account_count: int
    position_count: int
    last_synced_at: str | None = None
    change_amount: float
    change_pct: float
    allocation: list[InvestmentAllocationResult]
    top_positions: list[InvestmentPositionResult]
    history: list[InvestmentHistoryPointResult]


class ObjectiveResult(BaseModel):
    name: str
    tickers: list[dict]
    expected_return_pct: float | None
    volatility_pct: float | None
    sharpe: float | None


class PortfolioOptimizationResult(BaseModel):
    advanced_enabled: bool
    position_cap_pct: float
    objectives: list[ObjectiveResult]
    frontier_points: list[dict] | None
    sector_breakdown: list[dict] | None
    clip_log: list[dict]
    data_points: int
    insufficient_data: bool


class ProposalResult(BaseModel):
    """Result of staging a budget proposal for the user to apply in Ledger."""

    ok: bool
    proposal_id: int | None = None
    status: str | None = None
    summary: str | None = None
    month: str | None = None
    category_name: str | None = None
    category_key: str | None = None
    basis_limit: float | None = None
    proposed_limit: float | None = None
    apply_url: str | None = None
    message: str = ""
