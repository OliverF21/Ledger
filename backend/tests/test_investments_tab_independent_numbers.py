"""
Independent numerical audit of Investments-tab money-weighted return and CAGR.

Recomputes Excel-style XIRR and geometric TWR-CAGR from raw snapshots, then
compares to returns_service / risk_service — the same figures the Investments
page renders from GET /investments/risk/metrics.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from scipy.optimize import brentq  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Account, BalanceSnapshot, Base, InvestmentTransaction, Item, User  # noqa: E402
from app.services.returns_service import build_cagr, build_mwr_xirr, build_twr_series  # noqa: E402
from app.services.risk_service import build_risk_metrics  # noqa: E402


def _independent_xirr(dated_amounts: list[tuple[date, float]]) -> float:
    t0 = dated_amounts[0][0]

    def npv(rate: float) -> float:
        return sum(amt / ((1 + rate) ** ((d - t0).days / 365.0)) for d, amt in dated_amounts)

    return brentq(npv, -0.99, 10.0) * 100


def _independent_cagr(start_index: float, end_index: float, days: int) -> float:
    return ((end_index / start_index) ** (365.0 / days) - 1) * 100


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _brokerage(db, *, balance: str = "1000") -> Account:
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db.add(item)
    db.flush()
    acc = Account(
        item_id=item.id, plaid_account_id="acc-1", name="Brokerage",
        type="investment", current_balance=Decimal(balance),
    )
    db.add(acc)
    db.flush()
    return acc


def test_independent_xirr_matches_microsoft_excel_example():
    flows = [
        (date(2008, 1, 1), -10000.0),
        (date(2008, 3, 1), 2750.0),
        (date(2008, 10, 30), 4250.0),
        (date(2009, 2, 15), 3250.0),
        (date(2009, 4, 1), 2750.0),
    ]
    assert _independent_xirr(flows) == pytest.approx(37.3362533, abs=0.01)


def test_mwr_and_cagr_match_independent_on_ten_percent_year(db_session):
    acc = _brokerage(db_session)
    d0, d1 = date(2025, 1, 1), date(2026, 1, 1)
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1000, snapshot_date=d0))
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1100, snapshot_date=d1))
    db_session.commit()

    expected = _independent_xirr([(d0, -1000.0), (d1, 1100.0)])
    assert build_mwr_xirr(db_session, [acc.id], d0, d1) == pytest.approx(expected, abs=0.05)
    series = build_twr_series(db_session, [acc.id], d0, d1)
    assert build_cagr(series) == pytest.approx(expected, abs=0.05)


def test_cagr_uses_twr_not_naive_balance_ratio_when_cash_flows(db_session):
    acc = _brokerage(db_session, balance="2200")
    d0, d_mid, d1 = date(2025, 1, 1), date(2025, 7, 1), date(2026, 1, 1)
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1000, snapshot_date=d0))
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=2000, snapshot_date=d_mid))
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=2200, snapshot_date=d1))
    db_session.add(InvestmentTransaction(
        account_id=acc.id, plaid_investment_transaction_id="mid-dep",
        name="deposit", type="cash", subtype="deposit", amount=-1000, date=d_mid,
    ))
    db_session.commit()

    series = build_twr_series(db_session, [acc.id], d0, d1)
    got_cagr = build_cagr(series)
    got_mwr = build_mwr_xirr(db_session, [acc.id], d0, d1)
    naive = ((2200 / 1000) ** (365.0 / (d1 - d0).days) - 1) * 100
    indep_mwr = _independent_xirr([(d0, -1000.0), (d_mid, -1000.0), (d1, 2200.0)])

    assert series[-1].growth_index == pytest.approx(1.10, abs=0.001)
    assert got_cagr == pytest.approx(10.0, abs=0.05)
    assert naive == pytest.approx(120.0, abs=0.5)
    assert got_mwr == pytest.approx(indep_mwr, abs=0.05)
    assert got_mwr > got_cagr


def test_mwr_last_day_deposit_is_not_a_gain(db_session):
    acc = _brokerage(db_session, balance="1100")
    d0, d1 = date(2025, 1, 1), date(2026, 1, 1)
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1000, snapshot_date=d0))
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1100, snapshot_date=d1))
    db_session.add(InvestmentTransaction(
        account_id=acc.id, plaid_investment_transaction_id="last-dep",
        name="deposit", type="cash", subtype="deposit", amount=-100, date=d1,
    ))
    db_session.commit()

    expected = _independent_xirr([(d0, -1000.0), (d1, -100.0), (d1, 1100.0)])
    assert expected == pytest.approx(0.0, abs=0.05)
    assert build_mwr_xirr(db_session, [acc.id], d0, d1) == pytest.approx(expected, abs=0.05)


def test_risk_metrics_cagr_matches_independent_twr_annualization(db_session):
    acc = _brokerage(db_session)
    d0 = date.today() - timedelta(days=180)
    v = 1000.0
    for i in range(181):
        db_session.add(BalanceSnapshot(
            account_id=acc.id, balance=round(v, 4), snapshot_date=d0 + timedelta(days=i),
        ))
        v *= 1.0003
    db_session.commit()

    series = build_twr_series(db_session, [acc.id], d0, date.today())
    days = (series[-1].date - series[0].date).days
    expected = _independent_cagr(series[0].growth_index, series[-1].growth_index, days)
    risk = build_risk_metrics(db_session, lookback_days=365)
    assert risk.cagr_pct == pytest.approx(round(expected, 2), abs=0.02)
    assert risk.mwr_pct == pytest.approx(
        round(build_mwr_xirr(db_session, [acc.id], d0, date.today()), 2), abs=0.02,
    )
