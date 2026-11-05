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

Unspent and overspent amounts roll forward month by month. The stored limit
stays the planned monthly amount; `rollover` is the signed leftover from prior
months, and the spendable cap for a month is limit + rollover.
"""

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
    # Signed leftover from earlier months. Positive adds room; negative
    # reduces it. Not written back onto Budget.limit.
    rollover: float = 0.0
    virtual: bool = False


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

    Only the planned limit is copied. Leftover dollars are applied at read
    time as `rollover`, so editing a limit never bakes last month's surplus
    into the stored plan.
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


# (amount, plaid parent key, display category) for one expense.
SpendPart = tuple[float, str | None, str]


def _split_month(month_key: str) -> tuple[int, int]:
    return int(month_key[:4]), int(month_key[5:7])


def _next_month(month_key: str) -> str:
    year, month = _split_month(month_key)
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def _budget_identity(category_key: str | None, category_name: str | None) -> str:
    if category_key:
        return "k:" + normalize_category_key(category_key)
    return "n:" + (category_name or "").strip().lower()


def spendable_amount(limit: float, rollover: float, *, virtual: bool = False) -> float:
    """Cap for this month. Prior leftover is included; the Misc. bucket is not."""
    if virtual:
        return round(float(limit), 2)
    return round(float(limit) + float(rollover), 2)


def _match_target(
    category_key: str | None, category_name: str | None
) -> tuple[str | None, str | None]:
    """
    How a budget collects spend: a Plaid parent key, or a display name.

    Name-only budgets whose label is a PFC primary (e.g. "Travel") match every
    leaf under that primary, same as a keyed budget.
    """
    if category_key:
        return normalize_category_key(category_key), None
    resolved = normalize_category_key(resolve_category_to_pfc_key(category_name or ""))
    primary_label = CATEGORY_KEY_LABELS.get(resolved, "")
    name = (category_name or "").strip()
    if (
        resolved
        and (resolved in PLAID_PFC_PRIMARIES or resolved in KNOWN_CATEGORY_KEYS)
        and primary_label
        and primary_label.lower() == name.lower()
    ):
        return resolved, None
    return None, category_name or ""


def _eligible_parts(txns: list[Transaction]) -> list[tuple[date, float, str | None, str]]:
    parts: list[tuple[date, float, str | None, str]] = []
    for t in txns:
        rules_key = category_key_for_spending_rules(
            t.category_user, t.category_plaid, t.category_plaid_detailed
        )
        if is_excluded_from_budget_spending(rules_key):
            continue
        eff = float(t.amount) * float(t.user_split_pct or 1)
        display = t.display_category or "Uncategorized"
        parent = budget_parent_key(t.category_user, t.category_plaid, t.category_plaid_detailed)
        parts.append((t.date, eff, parent, display))
    return parts


def _spent_by_identity(budgets: list[Budget], parts: list[SpendPart]) -> dict[str, float]:
    spent_by_parent: dict[str, float] = {}
    spent_by_display: dict[str, float] = {}
    for eff, parent, display in parts:
        spent_by_display[display] = spent_by_display.get(display, 0.0) + eff
        if parent:
            spent_by_parent[parent] = spent_by_parent.get(parent, 0.0) + eff

    spent: dict[str, float] = {}
    for b in budgets:
        ident = _budget_identity(b.category_key, b.category_name)
        key, name = _match_target(b.category_key, b.category_name)
        if key:
            spent[ident] = spent_by_parent.get(key, 0.0)
        else:
            spent[ident] = spent_by_display.get(name or "", 0.0)
    return spent


def _plan_for_month(rows_by_month: dict[str, list[Budget]], month: str) -> list[Budget]:
    """Rows saved for `month`, or the latest earlier plan when the month was never opened."""
    own = rows_by_month.get(month)
    if own:
        return own
    prior = [m for m in rows_by_month if m < month]
    if not prior:
        return []
    return rows_by_month[max(prior)]


def _rollover_by_identity(
    rows_by_month: dict[str, list[Budget]],
    parts_by_month: dict[str, list[SpendPart]],
    month_key: str,
) -> dict[str, float]:
    """
    Signed leftover arriving in `month_key`, per category.

    A month's envelope is its limit plus whatever rolled in, minus what was
    spent. Months with no saved rows keep the previous plan, so a month the
    user never opened still consumes the budget. A saved month that omits a
    category ends that category's envelope.
    """
    if not rows_by_month:
        return {}
    first = min(rows_by_month)
    if first >= month_key:
        return {}

    running: dict[str, float] = {}
    cur = first
    while cur < month_key:
        plan = _plan_for_month(rows_by_month, cur)
        present = {
            _budget_identity(b.category_key, b.category_name): float(b.limit) for b in plan
        }
        for ident in list(running):
            if ident not in present:
                del running[ident]
        spent = _spent_by_identity(plan, parts_by_month.get(cur, []))
        for ident, limit in present.items():
            running[ident] = round(limit + running.get(ident, 0.0) - spent.get(ident, 0.0), 2)
        cur = _next_month(cur)
    return running


def _load_spend_parts(
    ldb: Session, start: date, end: date
) -> dict[str, list[SpendPart]]:
    # Positive amounts = debits/expenses in Plaid convention.
    # Pending counted so purchases hit budgets immediately (see analytics_service).
    txns = (
        ldb.query(Transaction)
        .filter(
            Transaction.removed == False,  # noqa: E712
            Transaction.hidden == False,  # noqa: E712
            Transaction.amount > 0,
            Transaction.date >= start,
            Transaction.date < end,
        )
        .all()
    )
    grouped: dict[str, list[SpendPart]] = {}
    for day, eff, parent, display in _eligible_parts(txns):
        key = f"{day.year:04d}-{day.month:02d}"
        grouped.setdefault(key, []).append((eff, parent, display))
    return grouped


def get_budget_items(bdb: Session, ldb: Session, month_key: str) -> list[BudgetItem]:
    """
    Per-category budget items (limit, rollover, spent) for a given month.
    Limits come from budgets.db; spending sums come from ledger.db (read-only).
    Shared by GET /budgets and the alert-computation endpoint.

    Spend that does not match any tracked budget lands in a virtual Misc. bucket
    so overall budget progress reflects all consumptive spending. Misc. does not
    roll into later months.
    """
    budgets = carry_forward_budgets(bdb, month_key)
    if not budgets:
        return []

    history = (
        bdb.query(Budget)
        .filter(Budget.user_id == 1, Budget.month <= month_key)
        .all()
    )
    rows_by_month: dict[str, list[Budget]] = {}
    for row in history:
        rows_by_month.setdefault(row.month, []).append(row)

    earliest = min(rows_by_month)
    start, _ = month_bounds(*_split_month(earliest))
    _, end = month_bounds(*_split_month(month_key))
    parts_by_month = _load_spend_parts(ldb, start, end)
    rollovers = _rollover_by_identity(rows_by_month, parts_by_month, month_key)
    current_parts = parts_by_month.get(month_key, [])
    spent_now = _spent_by_identity(budgets, current_parts)

    budget_items: list[BudgetItem] = []
    tracked_keys: set[str] = set()
    tracked_names: set[str] = set()
    for b in budgets:
        ident = _budget_identity(b.category_key, b.category_name)
        key, name = _match_target(b.category_key, b.category_name)
        if key:
            tracked_keys.add(key)
        elif name:
            tracked_names.add(name)
        budget_items.append(BudgetItem(
            id=b.id,
            category=b.category_name,
            limit=round(float(b.limit), 2),
            rollover=round(rollovers.get(ident, 0.0), 2),
            spent=round(spent_now.get(ident, 0.0), 2),
            color=b.color or CATEGORY_COLORS[0],
        ))

    misc_spent = 0.0
    for eff, parent, display in current_parts:
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

        # Spendable cap includes rolled leftover. Virtual Misc. has no limit.
        total_limit = round(
            sum(
                spendable_amount(bi.limit, bi.rollover, virtual=bi.virtual)
                for bi in budget_items
                if not bi.virtual
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
