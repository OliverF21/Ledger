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
    transaction_count: int = Field(
        description="How many transactions contributed to this category total"
    )


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
    allocation_nodes: list[CashFlowNodeResult] = Field(default_factory=list)


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
    mermaid: str = Field(
        description="Mermaid sankey-beta source (for debugging; prefer chart_cash_flow image)."
    )


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


class ProposalResult(BaseModel):
    """Result of staging a proposal for the user to apply in Ledger."""

    ok: bool
    proposal_id: int | None = None
    status: str | None = None
    summary: str | None = None
    kind: str | None = None
    month: str | None = None
    category_name: str | None = None
    category_key: str | None = None
    basis_limit: float | None = None
    proposed_limit: float | None = None
    goal_id: int | None = None
    goal_name: str | None = None
    transaction_id: int | None = None
    apply_url: str | None = None
    message: str = ""


class ResidualMonthResult(BaseModel):
    month: str
    residual: float
    income: float
    spending: float
    is_partial: bool


class PlanningCapacityResult(BaseModel):
    month: str
    lookback_months: int
    residual_this_month: float
    residual_lookback_avg: float | None = None
    recommended_available: float
    policy: str
    series: list[ResidualMonthResult]
    notes: list[str]


class GoalSpendCutInput(BaseModel):
    monthly_delta: float = Field(
        description=(
            "Change in monthly spending for this category. Negative reduces spend "
            "and frees capacity (e.g. -150 cuts $150/mo)."
        )
    )
    category_key: str | None = Field(
        default=None,
        description="Plaid PFC parent key, e.g. FOOD_AND_DRINK. Preferred when known.",
    )
    category_name: str | None = Field(
        default=None,
        description="Display name, e.g. 'Food & Drink' or 'Dining Out'.",
    )


class AppliedCutResult(BaseModel):
    category_key: str | None = None
    category_name: str
    monthly_delta: float
    matched_spend: float | None = None
    matched: bool
    note: str | None = None


class GoalScheduleRowResult(BaseModel):
    month_index: int
    month: str
    contribution: float
    interest: float
    balance: float
    contribution_cumulative: float
    interest_cumulative: float


class GoalPlanResult(BaseModel):
    mode: str
    target_amount: float
    current_amount: float
    remaining: float
    monthly_contribution: float
    months: int | None = None
    months_exact: float | None = None
    projected_end_month: str | None = None
    annual_return: float
    monthly_rate: float
    affordable: bool
    assumed_monthly_capacity: float | None = None
    capacity: PlanningCapacityResult | None = None
    schedule_summary: list[GoalScheduleRowResult]
    notes: list[str]
    assumptions: list[str]
    cuts: list[AppliedCutResult] = Field(default_factory=list)
    contribution_before_cuts: float | None = None
    months_before_cuts: int | None = None
    affordable_before_cuts: bool | None = None


class GoalProgressResult(BaseModel):
    id: int
    name: str
    kind: str
    kind_label: str
    target_amount: float
    opening_amount: float
    labeled_in: float
    labeled_out: float
    progress: float
    remaining: float
    monthly_contribution: float | None = None
    annual_return: float
    target_date: str | None = None
    status: str
    color: str
    months_remaining: int | None = None
    months_exact: float | None = None
    projected_end_month: str | None = None
    percent_funded: float


class GoalListResult(BaseModel):
    goals: list[GoalProgressResult]
