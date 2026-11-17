"""
Budget endpoints.
- GET /budgets?month=YYYY-MM : list budgets with pre-computed spent amounts
- GET /budgets/suggest        : income-based budget suggestions from spending history
- POST /budgets               : create a budget
- PUT /budgets/{id}           : update budget limit
- DELETE /budgets/{id}        : remove budget

Budgets are stored in budgets.db (separate from ledger.db) so Defender/AV
scanning the main transaction DB never blocks budget writes.
GET reads spending sums from ledger.db (read-only) and combines with limits
from budgets.db in Python.
"""

import zlib
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analytics_shared import (
    CATEGORY_COLORS,
    CATEGORY_KEY_LABELS,
    KNOWN_CATEGORY_KEYS,
    PLAID_PFC_PRIMARIES,
    budget_parent_key,
    category_key_for_income_rules,
    category_key_for_spending_rules,
    is_excluded_from_budget_spending,
    is_excluded_from_income,
    is_excluded_from_spending,
    month_bounds,
    normalize_category_key,
    resolve_category_to_pfc_key,
)
from app.budgets_db import Budget, get_budgets_db
from app.database import get_db
from app.errors import log_and_raise
from app.models import Transaction
from app.subscriptions import normalize_merchant, recurring_budget_lines

router = APIRouter(prefix="/budgets", tags=["budgets"])

# Virtual catch-all for spend that doesn't match any tracked budget category.
MISC_BUDGET_ID = -1
MISC_BUDGET_CATEGORY = "Misc."
MISC_BUDGET_COLOR = CATEGORY_COLORS[-1]  # muted slate


# ── Response models ───────────────────────────────────────────────────────────

class BudgetItem(BaseModel):
    id: int
    category: str
    limit: float
    spent: float
    color: str
    virtual: bool = False
    # Automatic envelope for a detected subscription. Virtual (not stored, not
    # editable) but unlike Misc. it has a real limit and counts toward the total.
    recurring: bool = False


def is_planned_budget_line(virtual: bool, recurring: bool = False) -> bool:
    """Misc. is unplanned spend. Recurring lines reserve their expected amount."""
    return not virtual or recurring


class BudgetsResponse(BaseModel):
    month: str
    budgets: list[BudgetItem]
    total_limit: float
    total_spent: float


# ── GET /budgets ──────────────────────────────────────────────────────────────

def carry_forward_budgets(bdb: Session, month_key: str) -> list[Budget]:
    """
    Ensure `month_key` has budget rows by copying the most recent prior month.

    Budgets are stored per YYYY-MM so spending stays month-scoped, but limits
    should persist across month boundaries — otherwise a new month opens empty
    even though the user already set Food/Transport/etc. last month.
    """
    existing = (
        bdb.query(Budget)
        .filter(Budget.user_id == 1, Budget.month == month_key)
        .all()
    )
    if existing:
        return existing

    prior_month = (
        bdb.query(Budget.month)
        .filter(Budget.user_id == 1, Budget.month < month_key)
        .order_by(Budget.month.desc())
        .limit(1)
        .scalar()
    )
    if not prior_month:
        return []

    source = (
        bdb.query(Budget)
        .filter(Budget.user_id == 1, Budget.month == prior_month)
        .all()
    )
    copied: list[Budget] = []
    for src in source:
        row = Budget(
            user_id=1,
            month=month_key,
            category_name=src.category_name,
            category_key=src.category_key,
            limit=src.limit,
            color=src.color,
        )
        bdb.add(row)
        copied.append(row)
    bdb.commit()
    for row in copied:
        bdb.refresh(row)
    return copied


def _budget_scope(budget: Budget) -> tuple[str, str]:
    """Return ('key', pfc_primary) or ('name', display label) for spend matching."""
    if budget.category_key:
        return "key", normalize_category_key(budget.category_key)
    # Name-only budgets whose label is a PFC primary (e.g. "Travel")
    # should match all leaf spend under that primary — not only rows
    # whose display_category string equals the label exactly.
    resolved = normalize_category_key(resolve_category_to_pfc_key(budget.category_name))
    primary_label = CATEGORY_KEY_LABELS.get(resolved, "")
    if (
        resolved
        and (resolved in PLAID_PFC_PRIMARIES or resolved in KNOWN_CATEGORY_KEYS)
        and primary_label
        and primary_label.lower() == (budget.category_name or "").strip().lower()
    ):
        return "key", resolved
    return "name", budget.category_name


def _recurring_already_budgeted(
    parent_key: str | None,
    category: str,
    tracked_keys: set[str],
    tracked_names: set[str],
) -> bool:
    """True when a category budget already captures this series' spend.

    Pulling it out again would reserve the same dollars twice.
    """
    if parent_key and normalize_category_key(parent_key) in tracked_keys:
        return True
    if category and category in tracked_names:
        return True
    resolved = normalize_category_key(resolve_category_to_pfc_key(category or ""))
    return bool(resolved) and resolved in tracked_keys


def _recurring_item_id(merchant_key: str, used: set[int]) -> int:
    candidate = -1000 - (zlib.crc32(merchant_key.encode("utf-8")) % 2_000_000_000)
    while candidate in used or candidate == MISC_BUDGET_ID:
        candidate -= 1
    used.add(candidate)
    return candidate


def get_budget_items(
    bdb: Session,
    ldb: Session,
    month_key: str,
    as_of: date | None = None,
) -> list[BudgetItem]:
    """
    Per-category budget items (limit + pre-computed spent) for a given month.
    Limits come from budgets.db; spending sums come from ledger.db (read-only).
    Shared by GET /budgets and the alert-computation endpoint.

    Spend that does not match any tracked budget lands in a virtual Misc. bucket
    so overall budget progress reflects all consumptive spending.

    Detected recurring charges that are not already inside a category budget
    become their own lines, limited to the amount expected that month, so
    subscriptions count toward the plan without a manual setup step.
    """
    today = as_of or date.today()
    budgets = carry_forward_budgets(bdb, month_key)

    year, mon = int(month_key[:4]), int(month_key[5:7])
    start, end = month_bounds(year, mon)

    scopes = [(b, *_budget_scope(b)) for b in budgets]
    tracked_keys = {value for _b, kind, value in scopes if kind == "key"}
    tracked_names = {value for _b, kind, value in scopes if kind == "name"}
    # A budget the user named after the merchant ("Netflix") already is that
    # subscription's envelope — don't add a second automatic line.
    named_by_key = {
        normalize_merchant(value): value
        for _b, kind, value in scopes
        if kind == "name" and normalize_merchant(value)
    }

    automatic = []
    named_recurring: dict[str, str] = {}
    for line in recurring_budget_lines(ldb, start, end, as_of=today):
        if _recurring_already_budgeted(line.parent_key, line.category, tracked_keys, tracked_names):
            continue
        named = named_by_key.get(line.merchant_key)
        if named:
            named_recurring[line.merchant_key] = named
            continue
        automatic.append(line)
    if not budgets and not automatic:
        return []

    # Load all expense transactions for the month from ledger.db (read-only).
    # Positive amounts = debits/expenses in Plaid convention.
    txns = (
        ldb.query(Transaction)
        .filter(
            Transaction.removed == False,
            # Pending counted so purchases hit budgets immediately (see analytics_service).
            Transaction.hidden == False,
            Transaction.amount > 0,
            Transaction.date >= start,
            Transaction.date < end,
        )
        .all()
    )

    # Two spending maps — use effective amount (respects user split).
    # Merchants with an automatic recurring line are kept out of category and
    # Misc. totals so the same charge is not counted twice.
    automatic_keys = {line.merchant_key for line in automatic}
    spent_by_plaid_parent: dict[str, float] = {}
    spent_by_display: dict[str, float] = {}
    recurring_spent: dict[str, float] = {line.merchant_key: 0.0 for line in automatic}
    eligible: list[tuple[float, str | None, str]] = []

    for t in txns:
        if is_excluded_from_budget_spending(
            category_key_for_spending_rules(t.category_user, t.category_plaid, t.category_plaid_detailed)
        ):
            continue
        eff = float(t.amount) * float(t.user_split_pct or 1)
        merchant_key = normalize_merchant(t.merchant or "")
        if merchant_key in named_recurring:
            display = named_recurring[merchant_key]
            spent_by_display[display] = spent_by_display.get(display, 0.0) + eff
            eligible.append((eff, None, display))
            continue
        if merchant_key in automatic_keys:
            recurring_spent[merchant_key] = recurring_spent.get(merchant_key, 0.0) + eff
            continue
        display = t.display_category or "Uncategorized"
        spent_by_display[display] = spent_by_display.get(display, 0.0) + eff
        parent = budget_parent_key(t.category_user, t.category_plaid, t.category_plaid_detailed)
        if parent:
            spent_by_plaid_parent[parent] = spent_by_plaid_parent.get(parent, 0.0) + eff
        eligible.append((eff, parent, display))

    budget_items: list[BudgetItem] = []
    for b, kind, value in scopes:
        if kind == "key":
            spent = spent_by_plaid_parent.get(value, 0.0)
        else:
            spent = spent_by_display.get(value, 0.0)
        budget_items.append(BudgetItem(
            id=b.id,
            category=b.category_name,
            limit=round(float(b.limit), 2),
            spent=round(spent, 2),
            color=b.color or CATEGORY_COLORS[0],
        ))

    # Misc. only exists once the user is actually budgeting. With no category
    # budgets, the plan is just the recurring charges detected below.
    if budgets:
        misc_spent = 0.0
        for eff, parent, display in eligible:
            if parent and parent in tracked_keys:
                continue
            if display in tracked_names:
                continue
            misc_spent += eff

        if misc_spent > 0:
            budget_items.append(BudgetItem(
                id=MISC_BUDGET_ID,
                category=MISC_BUDGET_CATEGORY,
                limit=0.0,
                spent=round(misc_spent, 2),
                color=MISC_BUDGET_COLOR,
                virtual=True,
            ))

    used_ids = {item.id for item in budget_items}
    for line in automatic:
        item_id = _recurring_item_id(line.merchant_key, used_ids)
        color_index = zlib.crc32(line.merchant_key.encode("utf-8")) % len(CATEGORY_COLORS)
        budget_items.append(BudgetItem(
            id=item_id,
            category=line.merchant or line.category or "Recurring",
            limit=line.expected_amount,
            spent=round(recurring_spent.get(line.merchant_key, 0.0), 2),
            color=CATEGORY_COLORS[color_index],
            virtual=True,
            recurring=True,
        ))
    return budget_items


@router.get("", response_model=BudgetsResponse)
async def get_budgets(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to current month"),
    bdb: Session = Depends(get_budgets_db),
    ldb: Session = Depends(get_db),
):
    """
    Returns all budgets for the given month with pre-computed spent amounts.
    Limits come from budgets.db; spending sums come from ledger.db.
    """
    try:
        if month:
            year, mon = int(month[:4]), int(month[5:7])
        else:
            today = date.today()
            year, mon = today.year, today.month
        month_key = f"{year:04d}-{mon:02d}"

        budget_items = get_budget_items(bdb, ldb, month_key)

        # Virtual Misc. has no limit. Recurring lines do, and they are part of the plan.
        total_limit = round(
            sum(
                bi.limit
                for bi in budget_items
                if is_planned_budget_line(bi.virtual, bi.recurring)
            ),
            2,
        )
        total_spent = round(sum(bi.spent for bi in budget_items), 2)

        return BudgetsResponse(
            month=month_key,
            budgets=budget_items,
            total_limit=total_limit,
            total_spent=total_spent,
        )

    except Exception as e:
        log_and_raise(e)


# ── Shared budget writer ──────────────────────────────────────────────────────

def _next_budget_color(bdb: Session) -> str:
    """Deterministic next color from the palette based on current budget count."""
    return CATEGORY_COLORS[bdb.query(Budget).filter(Budget.user_id == 1).count() % len(CATEGORY_COLORS)]


def upsert_budget(
    bdb: Session,
    *,
    month: str,
    category_name: str,
    limit: float,
    category_key: Optional[str] = None,
    color: Optional[str] = None,
) -> tuple[Budget, Optional[float], bool]:
    """
    Create-or-update a monthly budget, matching on (user_id, month, category_key)
    when a key is given, else on (user_id, month, category_name).

    Returns (budget, prev_limit, existed). `prev_limit` is the old limit when an
    existing budget was updated (None on create) — the caller uses it to build an
    undo record. This is the single in-process writer shared by the budget CRUD
    route and the proposal Apply endpoint; Apply must NOT call the HTTP route.
    """
    query = bdb.query(Budget).filter(Budget.user_id == 1, Budget.month == month)
    if category_key:
        existing = query.filter(Budget.category_key == category_key).first()
    else:
        existing = query.filter(Budget.category_name == category_name).first()

    if existing:
        prev_limit = float(existing.limit)
        existing.limit = limit
        # Keep the display label fresh, but never clobber an existing color.
        existing.category_name = category_name
        if category_key:
            existing.category_key = category_key
        if color and not existing.color:
            existing.color = color
        bdb.commit()
        bdb.refresh(existing)
        return existing, prev_limit, True

    budget = Budget(
        user_id=1,
        month=month,
        category_name=category_name,
        category_key=category_key,
        limit=limit,
        color=color or _next_budget_color(bdb),
    )
    bdb.add(budget)
    bdb.commit()
    bdb.refresh(budget)
    return budget, None, False


# ── CRUD (all writes go to budgets.db only) ───────────────────────────────────

class CreateBudgetRequest(BaseModel):
    category_name: str
    category_key: Optional[str] = None   # Plaid PFC key from suggest panel
    limit: float
    month: str                            # YYYY-MM
    color: Optional[str] = None


class UpdateBudgetRequest(BaseModel):
    limit: float


class BudgetMutateResponse(BaseModel):
    success: bool
    id: int


@router.post("", response_model=BudgetMutateResponse)
async def create_budget(req: CreateBudgetRequest, bdb: Session = Depends(get_budgets_db)):
    """Create a budget in budgets.db. No writes to ledger.db."""
    try:
        # Reject duplicate budget for same category+month
        existing = bdb.query(Budget).filter(
            Budget.user_id == 1,
            Budget.month == req.month,
            Budget.category_name == req.category_name,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Budget already exists for that category and month")

        color = req.color or CATEGORY_COLORS[bdb.query(Budget).filter(Budget.user_id == 1).count() % len(CATEGORY_COLORS)]
        budget = Budget(
            user_id=1,
            month=req.month,
            category_name=req.category_name,
            category_key=req.category_key,
            limit=req.limit,
            color=color,
        )
        bdb.add(budget)
        bdb.commit()
        bdb.refresh(budget)
        return BudgetMutateResponse(success=True, id=budget.id)
    except HTTPException:
        raise
    except Exception as e:
        bdb.rollback()
        log_and_raise(e)


@router.put("/{budget_id}", response_model=BudgetMutateResponse)
async def update_budget(budget_id: int, req: UpdateBudgetRequest, bdb: Session = Depends(get_budgets_db)):
    budget = bdb.query(Budget).filter(Budget.id == budget_id, Budget.user_id == 1).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    try:
        budget.limit = req.limit
        bdb.commit()
        return BudgetMutateResponse(success=True, id=budget.id)
    except Exception as e:
        bdb.rollback()
        log_and_raise(e)


@router.delete("/{budget_id}")
async def delete_budget(budget_id: int, bdb: Session = Depends(get_budgets_db)):
    budget = bdb.query(Budget).filter(Budget.id == budget_id, Budget.user_id == 1).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    try:
        bdb.delete(budget)
        bdb.commit()
        return {"success": True}
    except Exception as e:
        bdb.rollback()
        log_and_raise(e)


# ── Budget Suggester (reads ledger.db only) ───────────────────────────────────

# Suggested monthly allocations as % of take-home income.
SUGGESTED_ALLOCATIONS: List[dict] = [
    {"category": "RENT_AND_UTILITIES",  "label": "Rent & Utilities", "pct": 0.28, "color": "#5b8def"},
    {"category": "FOOD_AND_DRINK",      "label": "Food & Drink",     "pct": 0.12, "color": "#4fc4c4"},
    {"category": "TRANSPORTATION",      "label": "Transportation",   "pct": 0.10, "color": "#8a7df0"},
    {"category": "GENERAL_MERCHANDISE", "label": "Shopping",         "pct": 0.10, "color": "#d9a85b"},
    {"category": "ENTERTAINMENT",       "label": "Entertainment",    "pct": 0.05, "color": "#e7705f"},
    {"category": "PERSONAL_CARE",       "label": "Personal Care",    "pct": 0.04, "color": "#f0a87d"},
    {"category": "MEDICAL",             "label": "Medical",          "pct": 0.04, "color": "#7fb0ff"},
    {"category": "EDUCATION",           "label": "Education",        "pct": 0.02, "color": "#c084fc"},
    {"category": "PETS",                "label": "Pets",             "pct": 0.02, "color": "#a8d8a8"},
]


class SuggestedBudget(BaseModel):
    category: str
    label: str
    suggested: float
    actual_avg: float
    color: str


class SuggestResponse(BaseModel):
    avg_monthly_income: float
    months_sampled: int
    suggestions: List[SuggestedBudget]


@router.get("/suggest", response_model=SuggestResponse)
async def suggest_budgets(db: Session = Depends(get_db)):
    """
    Analyse the last 3 months of income and spending, then return
    per-category suggested limits based on standard allocation percentages.
    Reads from ledger.db only (no writes).
    """
    try:
        today = date.today()

        month_ranges = []
        for i in range(1, 4):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            start = date(y, m, 1)
            end = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)
            month_ranges.append((start, end))

        oldest = month_ranges[-1][0]
        newest = month_ranges[0][1]

        txns = (
            db.query(Transaction)
            .filter(
                Transaction.removed == False,
                Transaction.pending == False,
                Transaction.hidden == False,
                Transaction.date >= oldest,
                Transaction.date < newest,
            )
            .all()
        )

        income_total = 0.0
        parent_spend: dict[str, float] = {}
        for t in txns:
            income_category = category_key_for_income_rules(
                t.category_user, t.category_plaid, t.category_plaid_detailed
            )
            eff = float(t.amount) * float(t.user_split_pct or 1)
            if eff < 0 and not is_excluded_from_income(income_category):
                income_total += abs(eff)
            elif eff > 0 and not is_excluded_from_spending(
                category_key_for_spending_rules(t.category_user, t.category_plaid, t.category_plaid_detailed)
            ):
                parent = budget_parent_key(t.category_user, t.category_plaid, t.category_plaid_detailed)
                if parent:
                    parent_spend[parent] = parent_spend.get(parent, 0.0) + eff

        avg_income = income_total / len(month_ranges)

        avg_spend: dict[str, float] = {
            parent: round(amt / len(month_ranges), 2) for parent, amt in parent_spend.items()
        }

        suggestions = []
        for alloc in SUGGESTED_ALLOCATIONS:
            key = alloc["category"]
            suggestions.append(SuggestedBudget(
                category=key,
                label=alloc["label"],
                suggested=round(avg_income * alloc["pct"], 2),
                actual_avg=round(avg_spend.get(key, 0.0), 2),
                color=alloc["color"],
            ))

        return SuggestResponse(
            avg_monthly_income=round(avg_income, 2),
            months_sampled=len(month_ranges),
            suggestions=suggestions,
        )

    except Exception as e:
        log_and_raise(e)
