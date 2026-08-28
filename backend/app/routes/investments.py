"""
Investment holdings & activity endpoints.
- GET  /investments/summary      : portfolio totals + allocation by security type
- GET  /investments/holdings     : positions grouped by account
- GET  /investments/transactions : recent buy/sell/dividend activity
- GET  /investments/history      : portfolio value over time, from daily balance snapshots
- POST /investments/refresh      : on-demand Plaid refresh + resync for all real items
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.analytics_shared import CATEGORY_COLORS
from app.database import get_db
from app.errors import log_and_raise
from app.models import Account, Holding, InvestmentTransaction, Item, Security
from app.plaid_service import PlaidService
from app.security import decrypt_token
from app.services.investment_service import (
    _build_investment_history,
    _history_change,
    account_gross_holdings,
    investment_net_equity_total,
    scaled_holding_market_value,
)
from app.sync_engine import get_real_items, refresh_item_balances, sync_investments

router = APIRouter(prefix="/investments", tags=["investments"])


def _investment_accounts(db: Session) -> list[Account]:
    from app.crypto_tokens import PLAID_SYNC_EXCLUDED_ITEMS

    return (
        db.query(Account)
        .join(Item)
        .filter(
            Item.user_id == 1,
            Item.item_id.notin_(list(PLAID_SYNC_EXCLUDED_ITEMS)),
            Account.type == "investment",
        )
        .all()
    )


# ── GET /investments/summary ──────────────────────────────────────────────────

class AllocationSlice(BaseModel):
    type: str
    value: float
    pct: float
    color: str


class SummaryResponse(BaseModel):
    total_value: float
    total_cost_basis: Optional[float]
    unrealized_gain: Optional[float]
    allocation: list[AllocationSlice]
    account_count: int
    position_count: int
    last_synced_at: Optional[str]


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(db: Session = Depends(get_db)):
    try:
        accounts = _investment_accounts(db)
        account_ids = [a.id for a in accounts]

        holdings = (
            db.query(Holding)
            .options(joinedload(Holding.security))
            .filter(Holding.account_id.in_(account_ids))
            .all()
            if account_ids else []
        )

        accounts_by_id = {a.id: a for a in accounts}
        gross_by_account = account_gross_holdings(holdings)
        total_value = investment_net_equity_total(accounts)
        cost_basis_known = [h for h in holdings if h.cost_basis is not None]
        if cost_basis_known:
            total_cost_basis = sum(float(h.cost_basis) for h in cost_basis_known)
            value_of_known = sum(
                scaled_holding_market_value(h, accounts_by_id[h.account_id], gross_by_account)
                for h in cost_basis_known
            )
            unrealized_gain = value_of_known - total_cost_basis
        else:
            total_cost_basis = None
            unrealized_gain = None

        by_type: dict[str, float] = {}
        for h in holdings:
            key = (h.security.type if h.security else None) or "other"
            net_value = scaled_holding_market_value(h, accounts_by_id[h.account_id], gross_by_account)
            by_type[key] = by_type.get(key, 0.0) + net_value

        allocation = [
            AllocationSlice(
                type=t,
                value=round(v, 2),
                pct=round((v / total_value * 100) if total_value else 0, 1),
                color=CATEGORY_COLORS[i % len(CATEGORY_COLORS)],
            )
            for i, (t, v) in enumerate(sorted(by_type.items(), key=lambda kv: -kv[1]))
        ]

        last_synced = max(
            (a.item.last_synced_at for a in accounts if a.item.last_synced_at),
            default=None,
        )

        return SummaryResponse(
            total_value=round(total_value, 2),
            total_cost_basis=round(total_cost_basis, 2) if total_cost_basis is not None else None,
            unrealized_gain=round(unrealized_gain, 2) if unrealized_gain is not None else None,
            allocation=allocation,
            account_count=len(accounts),
            position_count=len(holdings),
            last_synced_at=last_synced.isoformat() if last_synced else None,
        )
    except Exception as e:
        log_and_raise(e)


# ── GET /investments/history ──────────────────────────────────────────────────

class HistoryPoint(BaseModel):
    date: str
    total: float


class HistoryResponse(BaseModel):
    snapshots: list[HistoryPoint]
    change_amount: float
    change_pct: float


@router.get("/history", response_model=HistoryResponse)
async def get_history(months: int = Query(6, ge=1, le=24), db: Session = Depends(get_db)):
    """
    Portfolio value over time. Uses daily BalanceSnapshot rows when they
    already span the requested window; otherwise marks current holdings to
    market (Plaid does not provide historical balances).
    """
    try:
        accounts = _investment_accounts(db)
        account_ids = [a.id for a in accounts]
        live_total = investment_net_equity_total(accounts)
        points = _build_investment_history(
            db, account_ids=account_ids, months=months, live_total=live_total
        )
        change_amount, change_pct = _history_change(points)
        return HistoryResponse(
            snapshots=[HistoryPoint(date=p.date, total=p.total) for p in points],
            change_amount=change_amount,
            change_pct=change_pct,
        )
    except Exception as e:
        log_and_raise(e)


# ── GET /investments/holdings ─────────────────────────────────────────────────

class Position(BaseModel):
    ticker: Optional[str]
    name: Optional[str]
    type: Optional[str]
    quantity: float
    price: Optional[float]
    value: float
    cost_basis: Optional[float]
    gain: Optional[float]
    gain_pct: Optional[float]
    currency: Optional[str]


class AccountHoldings(BaseModel):
    id: int
    name: str
    institution_name: Optional[str]
    subtype: Optional[str]
    total_value: float
    positions: list[Position]


class HoldingsResponse(BaseModel):
    accounts: list[AccountHoldings]


@router.get("/holdings", response_model=HoldingsResponse)
async def get_holdings(account_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    try:
        accounts = _investment_accounts(db)
        if account_id is not None:
            accounts = [a for a in accounts if a.id == account_id]

        result = []
        for account in accounts:
            holdings = (
                db.query(Holding)
                .options(joinedload(Holding.security))
                .filter(Holding.account_id == account.id)
                .all()
            )
            gross_by_account = account_gross_holdings(holdings)
            positions = []
            for h in holdings:
                value = scaled_holding_market_value(h, account, gross_by_account)
                cost_basis = float(h.cost_basis) if h.cost_basis is not None else None
                gain = (value - cost_basis) if cost_basis is not None else None
                gain_pct = (gain / cost_basis * 100) if gain is not None and cost_basis else None
                positions.append(Position(
                    ticker=h.security.ticker_symbol if h.security else None,
                    name=h.security.name if h.security else None,
                    type=h.security.type if h.security else None,
                    quantity=float(h.quantity),
                    price=float(h.institution_price) if h.institution_price is not None else None,
                    value=round(value, 2),
                    cost_basis=round(cost_basis, 2) if cost_basis is not None else None,
                    gain=round(gain, 2) if gain is not None else None,
                    gain_pct=round(gain_pct, 1) if gain_pct is not None else None,
                    currency=h.iso_currency_code or h.unofficial_currency_code,
                ))
            positions.sort(key=lambda p: -p.value)
            result.append(AccountHoldings(
                id=account.id,
                name=account.name,
                institution_name=account.item.institution_name,
                subtype=account.subtype,
                total_value=round(float(account.current_balance or 0), 2),
                positions=positions,
            ))

        return HoldingsResponse(accounts=result)
    except Exception as e:
        log_and_raise(e)


# ── GET /investments/transactions ─────────────────────────────────────────────

class InvestmentActivityItem(BaseModel):
    id: int
    account_name: str
    ticker: Optional[str]
    name: str
    type: str
    subtype: Optional[str]
    amount: float
    quantity: Optional[float]
    price: Optional[float]
    date: str


class InvestmentTransactionsResponse(BaseModel):
    transactions: list[InvestmentActivityItem]


@router.get("/transactions", response_model=InvestmentTransactionsResponse)
async def get_investment_transactions(months: int = Query(6, ge=1, le=24), db: Session = Depends(get_db)):
    try:
        accounts = _investment_accounts(db)
        account_ids = [a.id for a in accounts]
        accounts_by_id = {a.id: a for a in accounts}

        if not account_ids:
            return InvestmentTransactionsResponse(transactions=[])

        cutoff = date.today() - timedelta(days=months * 31)
        rows = (
            db.query(InvestmentTransaction)
            .options(joinedload(InvestmentTransaction.security))
            .filter(
                InvestmentTransaction.account_id.in_(account_ids),
                InvestmentTransaction.date >= cutoff,
            )
            .order_by(InvestmentTransaction.date.desc())
            .limit(200)
            .all()
        )

        return InvestmentTransactionsResponse(transactions=[
            InvestmentActivityItem(
                id=t.id,
                account_name=accounts_by_id[t.account_id].name,
                ticker=t.security.ticker_symbol if t.security else None,
                name=t.name,
                type=t.type,
                subtype=t.subtype,
                amount=float(t.amount),
                quantity=float(t.quantity) if t.quantity is not None else None,
                price=float(t.price) if t.price is not None else None,
                date=t.date.isoformat(),
            )
            for t in rows
        ])
    except Exception as e:
        log_and_raise(e)


# ── POST /investments/refresh ─────────────────────────────────────────────────

class RefreshResponse(BaseModel):
    refreshed_items: int
    holdings_upserted: int


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(db: Session = Depends(get_db)):
    try:
        real_items = get_real_items(db)
        refreshed = 0
        total_upserted = 0

        for item in real_items:
            try:
                access_token = decrypt_token(item.access_token_encrypted)
                try:
                    PlaidService.refresh_investments(access_token)
                except ValueError:
                    pass  # e.g. NO_INVESTMENT_ACCOUNTS for bank-only items
                refresh_item_balances(db, item, access_token)
                stats = sync_investments(db, item)
                total_upserted += stats.get("holdings_upserted", 0)
                refreshed += 1
            except Exception:
                db.rollback()
                continue

        return RefreshResponse(refreshed_items=refreshed, holdings_upserted=total_upserted)
    except Exception as e:
        log_and_raise(e)
