"""Pure time-value-of-money helpers for goal planning.

Ordinary annuity (end-of-month contributions), monthly compounding.
Sign convention: PV, PMT, and FV are non-negative amounts toward a savings goal.

Claude Desktop must not re-derive these; MCP tools call this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

MAX_ANNUAL_RETURN = 0.12
MAX_MONTHS = 600
_RATE_EPS = 1e-12
_MONEY_EPS = 1e-9


def money(value: float) -> float:
    """Round to cents, matching analytics_service totals."""
    return round(value + _MONEY_EPS, 2)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def clamp_annual_return(annual_return: float | None) -> float:
    """Return a yearly rate in [0, MAX_ANNUAL_RETURN]. None → 0."""
    if annual_return is None:
        return 0.0
    if annual_return < 0:
        raise ValueError("annual_return must be >= 0")
    if annual_return > MAX_ANNUAL_RETURN:
        raise ValueError(
            f"annual_return must be <= {MAX_ANNUAL_RETURN:.0%} " f"(pass 0.07 for 7%, not 7)"
        )
    return float(annual_return)


def monthly_rate(annual_return: float | None) -> float:
    return clamp_annual_return(annual_return) / 12.0


def fv(*, pv: float, pmt: float, n: float, monthly_rate: float) -> float:
    """Future value after n months of end-of-month contributions."""
    _require_non_negative(pv=pv, pmt=pmt, n=n)
    if n == 0:
        return money(pv)
    r = monthly_rate
    if abs(r) < _RATE_EPS:
        return money(pv + pmt * n)
    growth = (1.0 + r) ** n
    return money(pv * growth + pmt * (growth - 1.0) / r)


def pmt(*, pv: float, fv_target: float, n: float, monthly_rate: float) -> float:
    """Payment that grows PV to fv_target in n months."""
    _require_non_negative(pv=pv, n=n)
    if fv_target < 0:
        raise ValueError("fv_target must be >= 0")
    remaining = fv_target - pv
    if remaining <= _MONEY_EPS:
        return 0.0
    if n <= 0:
        raise ValueError("n must be > 0 to solve for a contribution")
    r = monthly_rate
    if abs(r) < _RATE_EPS:
        return money(remaining / n)
    growth = (1.0 + r) ** n
    return money((fv_target - pv * growth) * r / (growth - 1.0))


def nper(*, pv: float, fv_target: float, pmt: float, monthly_rate: float) -> float:
    """Exact (possibly fractional) months to grow PV to fv_target at pmt."""
    _require_non_negative(pv=pv, pmt=pmt)
    if fv_target < 0:
        raise ValueError("fv_target must be >= 0")
    if fv_target - pv <= _MONEY_EPS:
        return 0.0
    r = monthly_rate
    if pmt <= _MONEY_EPS:
        if abs(r) < _RATE_EPS or pv <= _MONEY_EPS:
            raise ValueError("monthly contribution must be > 0 to reach the goal")
        ratio = fv_target / pv
        if ratio <= 1:
            return 0.0
        return math.log(ratio) / math.log(1.0 + r)
    if abs(r) < _RATE_EPS:
        return (fv_target - pv) / pmt
    numerator = fv_target * r + pmt
    denominator = pv * r + pmt
    if denominator <= 0 or numerator <= 0:
        raise ValueError("contribution is too small to reach the goal under this return")
    ratio = numerator / denominator
    if ratio <= 1:
        return 0.0
    return math.log(ratio) / math.log(1.0 + r)


def months_to_goal(*, pv: float, fv_target: float, pmt: float, monthly_rate: float) -> int:
    """Ceil of nper, capped at MAX_MONTHS."""
    raw = nper(pv=pv, fv_target=fv_target, pmt=pmt, monthly_rate=monthly_rate)
    if raw <= _MONEY_EPS:
        return 0
    months = math.ceil(raw - 1e-9)
    return min(int(months), MAX_MONTHS)


@dataclass(frozen=True)
class ScheduleRow:
    month_index: int
    month: str
    contribution: float
    interest: float
    balance: float
    contribution_cumulative: float
    interest_cumulative: float


def build_schedule(
    *,
    pv: float,
    pmt: float,
    n: int,
    monthly_rate: float,
    start: date,
) -> list[ScheduleRow]:
    """Month-by-month balances for n end-of-month contributions starting at `start`."""
    _require_non_negative(pv=pv, pmt=pmt)
    if n < 0:
        raise ValueError("n must be >= 0")
    if n == 0:
        return []

    r = monthly_rate if abs(monthly_rate) >= _RATE_EPS else 0.0
    balance = pv
    contrib_cum = 0.0
    interest_cum = 0.0
    year, month = start.year, start.month
    rows: list[ScheduleRow] = []
    for index in range(1, n + 1):
        interest = money(balance * r) if r else 0.0
        balance = money(balance + interest + pmt)
        contrib_cum = money(contrib_cum + pmt)
        interest_cum = money(interest_cum + interest)
        rows.append(
            ScheduleRow(
                month_index=index,
                month=month_key(year, month),
                contribution=money(pmt),
                interest=interest,
                balance=balance,
                contribution_cumulative=contrib_cum,
                interest_cumulative=interest_cum,
            )
        )
        year, month = shift_month(year, month, 1)
    return rows


def schedule_milestones(rows: list[ScheduleRow]) -> list[ScheduleRow]:
    """First, quartile, and last rows — enough for Claude to narrate without 600 lines."""
    if not rows:
        return []
    n = len(rows)
    indexes = sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1})
    return [rows[i] for i in indexes]


def _require_non_negative(**kwargs: float) -> None:
    for name, value in kwargs.items():
        if value < 0:
            raise ValueError(f"{name} must be >= 0")
