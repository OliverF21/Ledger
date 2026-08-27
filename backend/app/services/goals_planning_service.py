"""Goal planning: capacity from cash flow + TVM schedules.

MCP tools wrap these builders. Claude must not invent NPER/PMT/FV.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.analytics_shared import (
    CATEGORY_KEY_LABELS,
    display_label_for_key,
    normalize_category_key,
    resolve_category_to_pfc_key,
)
from app.services.analytics_service import (
    CategorySpendItem,
    build_cash_flow,
    build_monthly_summary,
)
from app.services.tvm import (
    MAX_MONTHS,
    ScheduleRow,
    build_schedule,
    clamp_annual_return,
    money,
    month_key,
    monthly_rate as tvm_monthly_rate,
    months_to_goal,
    nper,
    pmt as tvm_pmt,
    schedule_milestones,
    shift_month,
)

PlanMode = Literal["time_to_goal", "required_contribution"]
CAPACITY_POLICY = "min(current, lookback)"


@dataclass(frozen=True)
class ResidualMonth:
    month: str
    residual: float
    income: float
    spending: float
    is_partial: bool


@dataclass(frozen=True)
class PlanningCapacity:
    month: str
    lookback_months: int
    residual_this_month: float
    residual_lookback_avg: float | None
    recommended_available: float
    series: list[ResidualMonth]
    notes: list[str]
    policy: str = CAPACITY_POLICY


@dataclass(frozen=True)
class SpendCut:
    monthly_delta: float
    category_key: str | None = None
    category_name: str | None = None


@dataclass(frozen=True)
class AppliedCut:
    category_key: str | None
    category_name: str
    monthly_delta: float
    matched_spend: float | None
    matched: bool
    note: str | None = None


@dataclass(frozen=True)
class GoalPlan:
    mode: str
    target_amount: float
    current_amount: float
    remaining: float
    monthly_contribution: float
    months: int | None
    months_exact: float | None
    projected_end_month: str | None
    annual_return: float
    monthly_rate: float
    affordable: bool
    capacity: PlanningCapacity | None
    assumed_monthly_capacity: float | None
    schedule_summary: list[ScheduleRow]
    notes: list[str]
    assumptions: list[str]
    cuts: list[AppliedCut]
    contribution_before_cuts: float | None = None
    months_before_cuts: int | None = None
    affordable_before_cuts: bool | None = None


def _anchor_month(month: str | None, today: date) -> tuple[int, int, str]:
    if month:
        try:
            parsed = date.fromisoformat(f"{month}-01")
        except ValueError as exc:
            raise ValueError("month must be in YYYY-MM format") from exc
        return parsed.year, parsed.month, f"{parsed.year:04d}-{parsed.month:02d}"
    return today.year, today.month, f"{today.year:04d}-{today.month:02d}"


def _is_partial_month(year: int, month: int, today: date) -> bool:
    return year == today.year and month == today.month


def _residual_for_month(db: Session, month: str) -> ResidualMonth:
    flow = build_cash_flow(db, month=month)
    return ResidualMonth(
        month=flow.month,
        residual=money(flow.savings),
        income=money(flow.total_income),
        spending=money(flow.total_spending),
        is_partial=False,
    )


def build_planning_capacity(
    db: Session,
    *,
    lookback_months: int = 3,
    month: str | None = None,
    today: date | None = None,
) -> PlanningCapacity:
    """Cash-flow residual capacity. recommended = min(current, lookback) when both exist."""
    if lookback_months < 1 or lookback_months > 24:
        raise ValueError("lookback_months must be between 1 and 24")

    today = today or date.today()
    year, mon, month_key_value = _anchor_month(month, today)
    partial = _is_partial_month(year, mon, today)

    current = _residual_for_month(db, month_key_value)
    current = replace(current, is_partial=partial)

    prior: list[ResidualMonth] = []
    for delta in range(1, lookback_months + 1):
        py, pm = shift_month(year, mon, -delta)
        row = _residual_for_month(db, month_key(py, pm))
        prior.append(row)
    prior.reverse()

    lookback_avg: float | None = None
    if prior:
        lookback_avg = money(sum(item.residual for item in prior) / len(prior))

    notes: list[str] = []
    if lookback_avg is None:
        recommended = current.residual
        notes.append("No complete lookback months; using current-month residual.")
    elif partial:
        recommended = lookback_avg
        notes.append(
            f"{month_key_value} is still in progress, so recommended capacity uses "
            "the lookback average rather than min(current, lookback)."
        )
    else:
        recommended = money(min(current.residual, lookback_avg))
        if current.residual + 0.005 < lookback_avg:
            notes.append(
                "Current-month residual is below the lookback average; "
                "using the lower current figure."
            )
        elif lookback_avg + 0.005 < current.residual:
            notes.append(
                "Lookback average is below the current-month residual; "
                "using the lower lookback figure."
            )

    if current.residual <= 0 and not partial:
        notes.append("Current-month residual is $0 — spending met or exceeded income.")

    series = [*prior, current]
    return PlanningCapacity(
        month=month_key_value,
        lookback_months=lookback_months,
        residual_this_month=current.residual,
        residual_lookback_avg=lookback_avg,
        recommended_available=money(max(recommended, 0.0)),
        series=series,
        notes=notes,
    )


def _norm_label(value: str) -> str:
    return " ".join(
        value.strip().lower().replace("&", "and").replace("_", " ").replace("-", " ").split()
    )


def _category_index(categories: list[CategorySpendItem]) -> dict[str, CategorySpendItem]:
    index: dict[str, CategorySpendItem] = {}
    for item in categories:
        index[_norm_label(item.name)] = item
        resolved = resolve_category_to_pfc_key(item.name)
        if resolved:
            index[_norm_label(resolved)] = item
            index[_norm_label(display_label_for_key(resolved))] = item
    for key, label in CATEGORY_KEY_LABELS.items():
        # Map known keys/labels onto a spend row if that rollup exists.
        hit = index.get(_norm_label(label)) or index.get(_norm_label(key))
        if hit is not None:
            index.setdefault(_norm_label(key), hit)
            index.setdefault(_norm_label(label), hit)
    return index


def _cut_tokens(cut: SpendCut) -> list[str]:
    tokens: list[str] = []
    if cut.category_key:
        key = normalize_category_key(cut.category_key.strip())
        tokens.append(key)
        tokens.append(display_label_for_key(key))
    if cut.category_name:
        tokens.append(cut.category_name)
        resolved = resolve_category_to_pfc_key(cut.category_name)
        if resolved:
            tokens.append(resolved)
            tokens.append(display_label_for_key(resolved))
    return tokens


def apply_spend_cuts(
    cuts: list[SpendCut],
    categories: list[CategorySpendItem],
) -> tuple[list[AppliedCut], float]:
    """Return applied cuts and the net change to monthly spend (negative frees capacity)."""
    if not cuts:
        return [], 0.0

    index = _category_index(categories)
    applied: list[AppliedCut] = []
    total_delta = 0.0

    for cut in cuts:
        if not cut.category_key and not cut.category_name:
            raise ValueError("each cut needs category_key or category_name")
        matched: CategorySpendItem | None = None
        for token in _cut_tokens(cut):
            matched = index.get(_norm_label(token))
            if matched is not None:
                break
        if matched is None:
            needle = _norm_label(cut.category_name or cut.category_key or "")
            for name, item in index.items():
                if needle and (needle in name or name in needle):
                    matched = item
                    break

        display = (
            matched.name
            if matched is not None
            else (cut.category_name or display_label_for_key(cut.category_key or "custom"))
        )
        key = cut.category_key
        if key:
            key = normalize_category_key(key)
        elif matched is not None:
            resolved = resolve_category_to_pfc_key(matched.name)
            key = resolved or None

        note = None
        if matched is None:
            note = f"No spending matched '{display}'; treating the cut as hypothetical."
        elif cut.monthly_delta < 0 and abs(cut.monthly_delta) > matched.value + 0.005:
            note = (
                f"Cut of ${abs(cut.monthly_delta):.2f} exceeds "
                f"${matched.value:.2f} typical spend in {display}."
            )

        applied.append(
            AppliedCut(
                category_key=key,
                category_name=display,
                monthly_delta=money(cut.monthly_delta),
                matched_spend=money(matched.value) if matched is not None else None,
                matched=matched is not None,
                note=note,
            )
        )
        total_delta += cut.monthly_delta

    return applied, money(total_delta)


def _months_from_target_date(target_date: date, today: date) -> int:
    months = (target_date.year - today.year) * 12 + (target_date.month - today.month)
    if months < 1:
        raise ValueError("target_date must be in a future calendar month")
    if months > MAX_MONTHS:
        raise ValueError(f"target_date is more than {MAX_MONTHS} months away")
    return months


def _assumptions(annual_return: float) -> list[str]:
    lines = [
        "Ordinary annuity: contributions at end of each month.",
        "Monthly compounding.",
    ]
    if annual_return <= 0:
        lines.append("Assumed annual return: 0% (cash / no growth).")
    else:
        lines.append(
            f"Assumed annual return: {annual_return:.1%} (user assumption, not a forecast)."
        )
    return lines


def _end_month(start: date, months: int) -> str | None:
    if months <= 0:
        return month_key(start.year, start.month)
    year, mon = shift_month(start.year, start.month, months - 1)
    return month_key(year, mon)


def build_goal_plan(
    *,
    target_amount: float,
    mode: PlanMode,
    current_amount: float = 0.0,
    monthly_contribution: float | None = None,
    months: int | None = None,
    target_date: date | None = None,
    annual_return: float | None = None,
    capacity: PlanningCapacity | None = None,
    assumed_monthly_capacity: float | None = None,
    cuts: list[AppliedCut] | None = None,
    today: date | None = None,
    contribution_before_cuts: float | None = None,
    months_before_cuts: int | None = None,
    affordable_before_cuts: bool | None = None,
) -> GoalPlan:
    today = today or date.today()
    if target_amount <= 0:
        raise ValueError("target_amount must be > 0")
    if current_amount < 0:
        raise ValueError("current_amount must be >= 0")
    if mode not in ("time_to_goal", "required_contribution"):
        raise ValueError("mode must be time_to_goal or required_contribution")

    rate_annual = clamp_annual_return(annual_return)
    r = tvm_monthly_rate(rate_annual)
    remaining = money(max(target_amount - current_amount, 0.0))
    notes: list[str] = list(capacity.notes) if capacity else []
    applied_cuts = cuts or []

    available: float | None
    if assumed_monthly_capacity is not None:
        if assumed_monthly_capacity < 0:
            raise ValueError("assumed_monthly_capacity must be >= 0")
        available = money(assumed_monthly_capacity)
        notes.append("Using caller-supplied assumed_monthly_capacity.")
    elif capacity is not None:
        available = capacity.recommended_available
    else:
        available = None

    contribution: float
    horizon: int | None
    exact: float | None

    if remaining <= 0:
        contribution = 0.0
        horizon = 0
        exact = 0.0
        notes.append("Goal is already funded.")
    elif mode == "time_to_goal":
        if monthly_contribution is not None:
            if monthly_contribution <= 0:
                raise ValueError("monthly_contribution must be > 0")
            contribution = money(monthly_contribution)
        elif available is not None:
            contribution = available
            notes.append("Using recommended capacity as the monthly contribution.")
        else:
            raise ValueError("time_to_goal needs monthly_contribution or a capacity figure")

        if contribution <= 0:
            horizon = None
            exact = None
            notes.append("No positive monthly contribution available; cannot project a timeline.")
        else:
            exact = nper(
                pv=current_amount,
                fv_target=target_amount,
                pmt=contribution,
                monthly_rate=r,
            )
            horizon = months_to_goal(
                pv=current_amount,
                fv_target=target_amount,
                pmt=contribution,
                monthly_rate=r,
            )
            if horizon >= MAX_MONTHS and exact > MAX_MONTHS:
                notes.append(f"Horizon capped at {MAX_MONTHS} months.")
    else:
        if months is not None and target_date is not None:
            raise ValueError("pass months or target_date, not both")
        if months is None and target_date is None:
            raise ValueError("required_contribution needs months or target_date")
        if months is not None:
            if months < 1:
                raise ValueError("months must be >= 1")
            horizon = int(months)
        else:
            assert target_date is not None
            horizon = _months_from_target_date(target_date, today)
        exact = float(horizon)
        contribution = tvm_pmt(
            pv=current_amount,
            fv_target=target_amount,
            n=horizon,
            monthly_rate=r,
        )
        if monthly_contribution is not None:
            notes.append(
                f"Ignoring monthly_contribution={monthly_contribution} in required_contribution mode."
            )

    affordable = True
    if remaining > 0 and available is not None:
        affordable = contribution <= available + 0.005
        if not affordable:
            gap = money(contribution - available)
            notes.append(
                f"Plan needs ${contribution:.2f}/mo vs ${available:.2f} available "
                f"(${gap:.2f}/mo short)."
            )

    schedule: list[ScheduleRow] = []
    if horizon and horizon > 0 and contribution > 0:
        schedule = build_schedule(
            pv=current_amount,
            pmt=contribution,
            n=horizon,
            monthly_rate=r,
            start=today.replace(day=1),
        )

    for cut in applied_cuts:
        if cut.note:
            notes.append(cut.note)

    return GoalPlan(
        mode=mode,
        target_amount=money(target_amount),
        current_amount=money(current_amount),
        remaining=remaining,
        monthly_contribution=money(contribution) if remaining > 0 else 0.0,
        months=horizon,
        months_exact=None if exact is None else round(exact, 4),
        projected_end_month=_end_month(today.replace(day=1), horizon or 0)
        if horizon is not None
        else None,
        annual_return=rate_annual,
        monthly_rate=r,
        affordable=affordable,
        capacity=capacity,
        assumed_monthly_capacity=(
            money(assumed_monthly_capacity) if assumed_monthly_capacity is not None else None
        ),
        schedule_summary=schedule_milestones(schedule),
        notes=notes,
        assumptions=_assumptions(rate_annual),
        cuts=applied_cuts,
        contribution_before_cuts=contribution_before_cuts,
        months_before_cuts=months_before_cuts,
        affordable_before_cuts=affordable_before_cuts,
    )


def plan_goal(
    db: Session | None,
    *,
    target_amount: float,
    mode: PlanMode,
    current_amount: float = 0.0,
    monthly_contribution: float | None = None,
    months: int | None = None,
    target_date: date | None = None,
    annual_return: float | None = None,
    assumed_monthly_capacity: float | None = None,
    lookback_months: int = 3,
    month: str | None = None,
    today: date | None = None,
) -> GoalPlan:
    """Run TVM. Loads Ledger capacity unless assumed_monthly_capacity is passed."""
    today = today or date.today()
    capacity: PlanningCapacity | None = None
    if assumed_monthly_capacity is None:
        if db is None:
            raise ValueError("ledger session required when assumed_monthly_capacity is omitted")
        capacity = build_planning_capacity(
            db,
            lookback_months=lookback_months,
            month=month,
            today=today,
        )
    return build_goal_plan(
        target_amount=target_amount,
        mode=mode,
        current_amount=current_amount,
        monthly_contribution=monthly_contribution,
        months=months,
        target_date=target_date,
        annual_return=annual_return,
        capacity=capacity,
        assumed_monthly_capacity=assumed_monthly_capacity,
        today=today,
    )


def plan_goal_from_expenses(
    db: Session,
    *,
    target_amount: float,
    mode: PlanMode,
    current_amount: float = 0.0,
    monthly_contribution: float | None = None,
    months: int | None = None,
    target_date: date | None = None,
    annual_return: float | None = None,
    cuts: list[SpendCut] | None = None,
    lookback_months: int = 3,
    month: str | None = None,
    today: date | None = None,
) -> GoalPlan:
    """Load capacity, apply optional spend cuts, then run TVM with before/after."""
    today = today or date.today()
    capacity = build_planning_capacity(
        db,
        lookback_months=lookback_months,
        month=month,
        today=today,
    )

    summary = build_monthly_summary(db, month=capacity.month)
    applied, spend_delta = apply_spend_cuts(cuts or [], summary.spending_by_category)

    extra = money(-spend_delta)  # negative spend delta frees capacity
    after_available = money(max(capacity.recommended_available + extra, 0.0))
    notes_extra: list[str] = []
    if extra:
        notes_extra.append(
            f"Spend cuts change monthly capacity by ${extra:.2f} "
            f"(from ${capacity.recommended_available:.2f} to ${after_available:.2f})."
        )

    after_capacity = replace(
        capacity,
        recommended_available=after_available,
        notes=[*capacity.notes, *notes_extra],
    )

    before = build_goal_plan(
        target_amount=target_amount,
        mode=mode,
        current_amount=current_amount,
        monthly_contribution=monthly_contribution,
        months=months,
        target_date=target_date,
        annual_return=annual_return,
        capacity=capacity,
        today=today,
    )
    after = build_goal_plan(
        target_amount=target_amount,
        mode=mode,
        current_amount=current_amount,
        monthly_contribution=monthly_contribution,
        months=months,
        target_date=target_date,
        annual_return=annual_return,
        capacity=after_capacity,
        cuts=applied,
        today=today,
        contribution_before_cuts=before.monthly_contribution,
        months_before_cuts=before.months,
        affordable_before_cuts=before.affordable,
    )
    return after
