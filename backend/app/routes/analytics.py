"""
Analytics endpoints — aggregated spending/income data from transactions.
- GET /analytics/summary: spending by category, KPIs, recent transactions for a given month
- GET /analytics/net-worth: balance snapshot history
- GET /analytics/trends: multi-month category spending
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.budgets_db import get_budgets_db
from app.database import get_db
from app.errors import log_and_raise
from app.services.analytics_service import build_cash_flow, build_monthly_summary, build_net_worth, build_trends

router = APIRouter(prefix="/analytics", tags=["analytics"])


class CategorySpend(BaseModel):
    name: str
    value: float
    color: str


class RecentTransaction(BaseModel):
    id: int
    merchant: str
    account_name: Optional[str]
    date: str
    category: Optional[str]
    amount: float
    initials: str


class MonthlySummaryResponse(BaseModel):
    month: str                          # "YYYY-MM"
    total_spending: float               # sum of expenses (positive number)
    total_income: float                 # sum of income
    savings_rate: float                 # (income - spending) / income * 100, or 0
    spending_by_category: list[CategorySpend]
    recent_transactions: list[RecentTransaction]
    prev_month_spending: float          # for % change calc on frontend


@router.get("/summary", response_model=MonthlySummaryResponse)
async def get_monthly_summary(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to current month"),
    db: Session = Depends(get_db),
):
    """
    Aggregate transactions for the given month into dashboard KPIs.
    Excludes removed/hidden transactions; pending transactions are counted.
    """
    try:
        summary = build_monthly_summary(db, month=month)
        return MonthlySummaryResponse(
            month=summary.month,
            total_spending=summary.total_spending,
            total_income=summary.total_income,
            savings_rate=summary.savings_rate,
            spending_by_category=[
                CategorySpend(name=item.name, value=item.value, color=item.color)
                for item in summary.spending_by_category
            ],
            recent_transactions=[
                RecentTransaction(
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
            prev_month_spending=summary.prev_month_spending,
        )

    except Exception as e:
        log_and_raise(e)


# ── Net Worth ──────────────────────────────────────────────────────────────────

class NetWorthSnapshot(BaseModel):
    date: str
    total: float


class AccountBreakdown(BaseModel):
    id: int
    name: str
    type: str
    subtype: Optional[str]
    balance: float   # always absolute value
    is_liability: bool


class NetWorthResponse(BaseModel):
    current_net_worth: float
    total_assets: float
    total_liabilities: float
    accounts: list[AccountBreakdown]
    snapshots: list[NetWorthSnapshot]
    change_amount: float
    change_pct: float


@router.get("/net-worth", response_model=NetWorthResponse)
async def get_net_worth(
    months: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """Historical net worth from daily balance snapshots."""
    try:
        result = build_net_worth(db, months=months)
        return NetWorthResponse(
            current_net_worth=result.current_net_worth,
            total_assets=result.total_assets,
            total_liabilities=result.total_liabilities,
            accounts=[
                AccountBreakdown(
                    id=item.id,
                    name=item.name,
                    type=item.type,
                    subtype=item.subtype,
                    balance=item.balance,
                    is_liability=item.is_liability,
                )
                for item in result.accounts
            ],
            snapshots=[
                NetWorthSnapshot(date=item.date, total=item.total)
                for item in result.snapshots
            ],
            change_amount=result.change_amount,
            change_pct=result.change_pct,
        )

    except Exception as e:
        log_and_raise(e)


# ── Trends ─────────────────────────────────────────────────────────────────────

class TrendMonth(BaseModel):
    month_key: str          # "2026-01"
    label: str              # "Jan"
    full_label: str         # "Jan 2026"
    total_spending: float
    total_income: float
    net: float
    is_partial: bool


class TrendCategory(BaseModel):
    name: str
    color: str
    monthly: list[float]
    total: float
    monthly_avg: float
    share_pct: float
    last_full: float
    prior_avg: float
    change_vs_prior_pct: Optional[float]


class TrendsResponse(BaseModel):
    months: list[TrendMonth]
    categories: list[TrendCategory]
    period_spending: float
    period_income: float
    monthly_avg_spending: float
    prev_monthly_avg_spending: float
    spending_change_pct: Optional[float]


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    months: int = Query(6, ge=3, le=24),
    db: Session = Depends(get_db),
):
    """Multi-month spending/income trends with per-category series and stats."""
    try:
        trends = build_trends(db, months=months)
        return TrendsResponse(
            months=[TrendMonth(**vars(m)) for m in trends.months],
            categories=[TrendCategory(**vars(c)) for c in trends.categories],
            period_spending=trends.period_spending,
            period_income=trends.period_income,
            monthly_avg_spending=trends.monthly_avg_spending,
            prev_monthly_avg_spending=trends.prev_monthly_avg_spending,
            spending_change_pct=trends.spending_change_pct,
        )

    except Exception as e:
        log_and_raise(e)


# ── Cash Flow (Sankey data) ────────────────────────────────────────────────────

class CashFlowTxn(BaseModel):
    merchant: str
    amount: float
    date: str


class CashFlowNode(BaseModel):
    id: str
    label: str
    amount: float
    color: str
    top_transactions: list[CashFlowTxn] = []


class CashFlowResponse(BaseModel):
    month: str
    total_income: float
    total_spending: float
    savings: float
    income_sources: list[CashFlowNode]
    spending_categories: list[CashFlowNode]
    allocation_nodes: list[CashFlowNode] = []


def _cash_flow_node(node) -> CashFlowNode:
    return CashFlowNode(
        id=node.id,
        label=node.label,
        amount=node.amount,
        color=node.color,
        top_transactions=[
            CashFlowTxn(merchant=txn.merchant, amount=txn.amount, date=txn.date)
            for txn in node.top_transactions
        ],
    )


@router.get("/cash-flow", response_model=CashFlowResponse)
async def get_cash_flow(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to current month"),
    db: Session = Depends(get_db),
    bdb: Session = Depends(get_budgets_db),
):
    """Income sources, consumptive spending, and named allocation sinks for the Sankey."""
    try:
        cash_flow = build_cash_flow(db, month=month, goals_db=bdb)
        return CashFlowResponse(
            month=cash_flow.month,
            total_income=cash_flow.total_income,
            total_spending=cash_flow.total_spending,
            savings=cash_flow.savings,
            income_sources=[_cash_flow_node(node) for node in cash_flow.income_sources],
            spending_categories=[_cash_flow_node(node) for node in cash_flow.spending_categories],
            allocation_nodes=[_cash_flow_node(node) for node in cash_flow.allocation_nodes],
        )

    except Exception as e:
        log_and_raise(e)
