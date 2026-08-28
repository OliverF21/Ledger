"""Financial goals, labeled-transfer progress, and shared writers for REST + Advisor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.analytics_shared import CATEGORY_COLORS
from app.budgets_db import GOAL_KINDS, GOAL_STATUSES, FinancialGoal
from app.models import GoalAttribution, Transaction
from app.services.tvm import money, months_to_goal, monthly_rate, nper, shift_month

GOAL_KIND_LABELS = {
    "emergency_fund": "Emergency fund",
    "sinking_fund": "Sinking fund",
    "debt_payoff": "Debt payoff",
    "invest": "Invest",
    "custom": "Custom",
}


def _goal_color(index: int, explicit: str | None) -> str:
    if explicit:
        return explicit
    return CATEGORY_COLORS[index % len(CATEGORY_COLORS)]


def _effective_amount(txn: Transaction) -> float:
    pct = float(txn.user_split_pct) if txn.user_split_pct is not None else 1.0
    return abs(float(txn.amount)) * pct


def labeled_totals(ledger_db: Session, goal_id: int) -> tuple[float, float]:
    """Sum labeled inflows (positive txn amount = cash leaving spendable) vs withdrawals."""
    rows = (
        ledger_db.query(GoalAttribution, Transaction)
        .join(Transaction, Transaction.id == GoalAttribution.transaction_id)
        .filter(
            GoalAttribution.goal_id == goal_id,
            Transaction.removed.is_(False),
            Transaction.hidden.is_(False),
        )
        .all()
    )
    labeled_in = 0.0
    labeled_out = 0.0
    for attr, txn in rows:
        amt = money(float(attr.amount))
        if float(txn.amount) >= 0:
            labeled_in += amt
        else:
            labeled_out += amt
    return money(labeled_in), money(labeled_out)


@dataclass
class GoalProgress:
    id: int
    name: str
    kind: str
    target_amount: float
    opening_amount: float
    labeled_in: float
    labeled_out: float
    progress: float
    remaining: float
    monthly_contribution: float | None
    annual_return: float
    target_date: str | None
    status: str
    color: str
    months_remaining: int | None
    months_exact: float | None
    projected_end_month: str | None
    percent_funded: float


def build_goal_progress(
    goal: FinancialGoal,
    ledger_db: Session,
    *,
    today: date | None = None,
    color_index: int = 0,
) -> GoalProgress:
    today = today or date.today()
    opening = money(float(goal.current_amount or 0))
    labeled_in, labeled_out = labeled_totals(ledger_db, goal.id)
    progress = money(max(opening + labeled_in - labeled_out, 0.0))
    target = money(float(goal.target_amount))
    remaining = money(max(target - progress, 0.0))
    pmt = float(goal.monthly_contribution) if goal.monthly_contribution is not None else None
    r_annual = float(goal.annual_return_assumption or 0)
    r = monthly_rate(r_annual)
    months = None
    exact = None
    end = None
    if remaining <= 0:
        months = 0
        exact = 0.0
        end = f"{today.year:04d}-{today.month:02d}"
    elif pmt and pmt > 0:
        exact = nper(pv=progress, fv_target=target, pmt=pmt, monthly_rate=r)
        months = months_to_goal(pv=progress, fv_target=target, pmt=pmt, monthly_rate=r)
        if months and months > 0:
            y, m = shift_month(today.year, today.month, months - 1)
            end = f"{y:04d}-{m:02d}"
    pct = round(progress / target * 100, 1) if target > 0 else 0.0
    return GoalProgress(
        id=goal.id,
        name=goal.name,
        kind=goal.kind,
        target_amount=target,
        opening_amount=opening,
        labeled_in=labeled_in,
        labeled_out=labeled_out,
        progress=progress,
        remaining=remaining,
        monthly_contribution=money(pmt) if pmt is not None else None,
        annual_return=r_annual,
        target_date=goal.target_date,
        status=goal.status,
        color=_goal_color(color_index, goal.color),
        months_remaining=months,
        months_exact=None if exact is None else round(exact, 4),
        projected_end_month=end,
        percent_funded=pct,
    )


def list_goal_progress(
    budgets_db: Session,
    ledger_db: Session,
    *,
    include_dismissed: bool = False,
    today: date | None = None,
) -> list[GoalProgress]:
    q = budgets_db.query(FinancialGoal).filter(FinancialGoal.user_id == 1)
    if not include_dismissed:
        q = q.filter(FinancialGoal.status != "dismissed")
    goals = q.order_by(FinancialGoal.created_at.asc()).all()
    return [
        build_goal_progress(g, ledger_db, today=today, color_index=i)
        for i, g in enumerate(goals)
    ]


def get_goal(budgets_db: Session, goal_id: int) -> FinancialGoal:
    goal = (
        budgets_db.query(FinancialGoal)
        .filter(FinancialGoal.id == goal_id, FinancialGoal.user_id == 1)
        .first()
    )
    if goal is None:
        raise ValueError("Goal not found")
    return goal


def upsert_goal(
    budgets_db: Session,
    *,
    goal_id: int | None = None,
    name: str,
    kind: str = "custom",
    target_amount: float,
    current_amount: float = 0.0,
    target_date: str | None = None,
    monthly_contribution: float | None = None,
    annual_return_assumption: float | None = None,
    status: str = "active",
    color: str | None = None,
) -> tuple[FinancialGoal, dict[str, Any] | None, bool]:
    """Create or update a goal. Returns (goal, previous snapshot or None, created)."""
    name = name.strip()
    if not name:
        raise ValueError("name is required")
    if kind not in GOAL_KINDS:
        raise ValueError(f"kind must be one of {GOAL_KINDS}")
    if status not in GOAL_STATUSES:
        raise ValueError(f"status must be one of {GOAL_STATUSES}")
    if target_amount <= 0:
        raise ValueError("target_amount must be > 0")
    if current_amount < 0:
        raise ValueError("current_amount must be >= 0")
    if monthly_contribution is not None and monthly_contribution < 0:
        raise ValueError("monthly_contribution must be >= 0")
    if annual_return_assumption is not None and (
        annual_return_assumption < 0 or annual_return_assumption > 0.12
    ):
        raise ValueError("annual_return_assumption must be between 0 and 0.12")

    created = False
    prev: dict[str, Any] | None = None
    if goal_id is None:
        goal = FinancialGoal(
            user_id=1,
            name=name,
            kind=kind,
            target_amount=target_amount,
            current_amount=current_amount,
            target_date=target_date,
            monthly_contribution=monthly_contribution,
            annual_return_assumption=annual_return_assumption,
            status=status,
            color=color,
        )
        budgets_db.add(goal)
        budgets_db.flush()
        created = True
    else:
        goal = get_goal(budgets_db, goal_id)
        prev = _snapshot(goal)
        goal.name = name
        goal.kind = kind
        goal.target_amount = target_amount
        goal.current_amount = current_amount
        goal.target_date = target_date
        goal.monthly_contribution = monthly_contribution
        goal.annual_return_assumption = annual_return_assumption
        goal.status = status
        if color is not None:
            goal.color = color
    return goal, prev, created


def restore_goal_snapshot(budgets_db: Session, snapshot: dict[str, Any]) -> None:
    goal = get_goal(budgets_db, int(snapshot["id"]))
    goal.name = snapshot["name"]
    goal.kind = snapshot["kind"]
    goal.target_amount = snapshot["target_amount"]
    goal.current_amount = snapshot["current_amount"]
    goal.target_date = snapshot["target_date"]
    goal.monthly_contribution = snapshot["monthly_contribution"]
    goal.annual_return_assumption = snapshot["annual_return_assumption"]
    goal.status = snapshot["status"]
    goal.color = snapshot["color"]


def delete_created_goal(budgets_db: Session, goal_id: int) -> None:
    goal = get_goal(budgets_db, goal_id)
    budgets_db.delete(goal)


def set_goal_contribution(
    budgets_db: Session, goal_id: int, monthly_contribution: float
) -> tuple[FinancialGoal, float | None]:
    if monthly_contribution <= 0:
        raise ValueError("monthly_contribution must be > 0")
    goal = get_goal(budgets_db, goal_id)
    prev = float(goal.monthly_contribution) if goal.monthly_contribution is not None else None
    goal.monthly_contribution = monthly_contribution
    return goal, prev


def attributions_for_transaction(ledger_db: Session, transaction_id: int) -> list[GoalAttribution]:
    return (
        ledger_db.query(GoalAttribution)
        .filter(GoalAttribution.transaction_id == transaction_id)
        .all()
    )


def replace_txn_attributions(
    ledger_db: Session,
    budgets_db: Session,
    transaction_id: int,
    items: list[tuple[int, float]],
) -> list[dict[str, Any]]:
    """Replace labels on a transaction. Returns the previous attribution list."""
    txn = (
        ledger_db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.removed.is_(False))
        .first()
    )
    if txn is None:
        raise ValueError("Transaction not found")
    cap = _effective_amount(txn)
    total = sum(amount for _, amount in items)
    if any(amount <= 0 for _, amount in items):
        raise ValueError("each attribution amount must be > 0")
    if total - cap > 0.02:
        raise ValueError(f"attributions ${total:.2f} exceed transaction ${cap:.2f}")

    active_ids = {
        g.id
        for g in budgets_db.query(FinancialGoal)
        .filter(FinancialGoal.user_id == 1, FinancialGoal.status.in_(("active", "paused")))
        .all()
    }
    for goal_id, _ in items:
        if goal_id not in active_ids:
            raise ValueError(f"goal {goal_id} is not an active goal")

    prior = [
        {"goal_id": a.goal_id, "amount": money(float(a.amount))}
        for a in attributions_for_transaction(ledger_db, transaction_id)
    ]
    ledger_db.query(GoalAttribution).filter(
        GoalAttribution.transaction_id == transaction_id
    ).delete()
    for goal_id, amount in items:
        ledger_db.add(
            GoalAttribution(
                transaction_id=transaction_id,
                goal_id=goal_id,
                amount=money(amount),
            )
        )
    ledger_db.flush()
    return prior


def attributions_by_transaction_ids(
    ledger_db: Session, txn_ids: list[int]
) -> dict[int, list[GoalAttribution]]:
    if not txn_ids:
        return {}
    rows = (
        ledger_db.query(GoalAttribution)
        .filter(GoalAttribution.transaction_id.in_(txn_ids))
        .all()
    )
    out: dict[int, list[GoalAttribution]] = {}
    for row in rows:
        out.setdefault(row.transaction_id, []).append(row)
    return out


def goal_name_map(budgets_db: Session) -> dict[int, FinancialGoal]:
    return {g.id: g for g in budgets_db.query(FinancialGoal).filter(FinancialGoal.user_id == 1).all()}


def snapshot_goal(goal: FinancialGoal) -> dict[str, Any]:
    return {
        "id": goal.id,
        "name": goal.name,
        "kind": goal.kind,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount or 0),
        "target_date": goal.target_date,
        "monthly_contribution": (
            float(goal.monthly_contribution) if goal.monthly_contribution is not None else None
        ),
        "annual_return_assumption": (
            float(goal.annual_return_assumption) if goal.annual_return_assumption is not None else None
        ),
        "status": goal.status,
        "color": goal.color,
    }


def _snapshot(goal: FinancialGoal) -> dict[str, Any]:
    return snapshot_goal(goal)


def _num_eq(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return a == b


def snapshots_equal(current: dict[str, Any], applied: dict[str, Any]) -> bool:
    """True when the live goal still matches the snapshot written at Apply."""
    keys = (
        "name",
        "kind",
        "target_amount",
        "current_amount",
        "target_date",
        "monthly_contribution",
        "annual_return_assumption",
        "status",
        "color",
    )
    for key in keys:
        va, vb = current.get(key), applied.get(key)
        if key in {"target_amount", "current_amount", "monthly_contribution", "annual_return_assumption"}:
            if not _num_eq(va, vb):
                return False
        elif va != vb:
            return False
    return True


def attribution_dicts(rows: list[GoalAttribution] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append({"goal_id": int(row["goal_id"]), "amount": money(float(row["amount"]))})
        else:
            out.append({"goal_id": int(row.goal_id), "amount": money(float(row.amount))})
    return out


def attributions_equal(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    def norm(rows: list[dict[str, Any]]) -> list[tuple[int, float]]:
        return sorted(
            (int(r["goal_id"]), round(float(r["amount"]), 2)) for r in rows
        )

    return norm(a) == norm(b)
