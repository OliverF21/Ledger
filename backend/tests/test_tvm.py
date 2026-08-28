from __future__ import annotations

import math

import pytest

from app.services import tvm


def test_zero_rate_nper_and_pmt():
    assert tvm.nper(pv=2400, fv_target=10000, pmt=650, monthly_rate=0) == pytest.approx(7600 / 650)
    assert tvm.months_to_goal(pv=2400, fv_target=10000, pmt=650, monthly_rate=0) == 12
    assert tvm.pmt(pv=2400, fv_target=10000, n=12, monthly_rate=0) == 633.33


def test_zero_rate_fv():
    assert tvm.fv(pv=0, pmt=500, n=20, monthly_rate=0) == 10000.00


def test_already_funded():
    assert tvm.nper(pv=10000, fv_target=10000, pmt=100, monthly_rate=0) == 0
    assert tvm.pmt(pv=10000, fv_target=8000, n=12, monthly_rate=0) == 0
    assert tvm.months_to_goal(pv=12000, fv_target=10000, pmt=100, monthly_rate=0) == 0


def test_pmt_inverts_fv_with_return():
    r = 0.05 / 12
    payment = tvm.pmt(pv=0, fv_target=50000, n=60, monthly_rate=r)
    assert tvm.fv(pv=0, pmt=payment, n=60, monthly_rate=r) == pytest.approx(50000, abs=0.2)


def test_nper_inverts_fv_with_return():
    r = 0.07 / 12
    months = tvm.nper(pv=1000, fv_target=20000, pmt=250, monthly_rate=r)
    assert tvm.fv(pv=1000, pmt=250, n=months, monthly_rate=r) == pytest.approx(20000, abs=0.05)


def test_zero_contribution_without_growth_errors():
    with pytest.raises(ValueError, match="monthly contribution"):
        tvm.nper(pv=100, fv_target=1000, pmt=0, monthly_rate=0)


def test_zero_contribution_with_growth_uses_compounding():
    r = 0.06 / 12
    n = tvm.nper(pv=10000, fv_target=20000, pmt=0, monthly_rate=r)
    assert n == pytest.approx(math.log(2) / math.log(1 + r))


def test_clamp_annual_return():
    assert tvm.clamp_annual_return(None) == 0.0
    assert tvm.clamp_annual_return(0.07) == 0.07
    with pytest.raises(ValueError, match="0.07"):
        tvm.clamp_annual_return(7)
    with pytest.raises(ValueError, match=">= 0"):
        tvm.clamp_annual_return(-0.01)


def test_schedule_accumulates_interest():
    rows = tvm.build_schedule(
        pv=1000,
        pmt=100,
        n=3,
        monthly_rate=0.01,
        start=__import__("datetime").date(2026, 1, 1),
    )
    assert len(rows) == 3
    assert rows[0].month == "2026-01"
    assert rows[0].interest == 10.00
    assert rows[0].balance == 1110.00
    assert rows[-1].month == "2026-03"
    summary = tvm.schedule_milestones(rows)
    assert summary[0] is rows[0]
    assert summary[-1] is rows[-1]
