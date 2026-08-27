# backend/tests/test_returns_service.py
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Account, BalanceSnapshot, Base, InvestmentTransaction, Item, User
from app.services.returns_service import build_cagr, build_mwr_xirr, build_twr_series, external_cash_flows


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'returns.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def account(db_session):
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    acc = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment")
    db_session.add(acc)
    db_session.commit()
    return acc


def _snapshot(db, account, day, balance):
    db.add(BalanceSnapshot(account_id=account.id, balance=balance, snapshot_date=day))


def test_twr_ignores_deposit_inflating_return(db_session, account):
    d0 = date(2026, 1, 1)
    # Day 0: $100. Day 1: still $100 of market value, but a $50 deposit lands,
    # taking the balance to $150. Day 2: market drops 2% on the new $150 base -> $147.
    _snapshot(db_session, account, d0, 100)
    _snapshot(db_session, account, d0 + timedelta(days=1), 150)
    db_session.add(InvestmentTransaction(
        account_id=account.id, plaid_investment_transaction_id="txn-1",
        name="deposit", type="cash", subtype="deposit", amount=-50, date=d0 + timedelta(days=1),
    ))
    _snapshot(db_session, account, d0 + timedelta(days=2), 147)
    db_session.commit()

    series = build_twr_series(db_session, [account.id], d0, d0 + timedelta(days=2))

    assert len(series) == 3
    # Day 1 sub-period return should be ~0% (the deposit is excluded), not +50%.
    assert series[1].growth_index == pytest.approx(1.0, abs=0.001)
    # Day 2 sub-period return is -2% on top of that.
    assert series[2].growth_index == pytest.approx(0.98, abs=0.001)


def test_twr_treats_dividend_as_real_return_not_external_flow(db_session, account):
    # Day 0: $100. Day 1: a $50 dividend lands (type="cash", subtype="dividend")
    # and the balance rises to $150 purely because of it. Since a dividend is
    # investment income already reflected in the balance -- not an external
    # deposit -- it must NOT be excluded from the day's TWR sub-period return:
    # the day should read as a real +50% gain, not 0%.
    d0 = date(2026, 1, 1)
    _snapshot(db_session, account, d0, 100)
    _snapshot(db_session, account, d0 + timedelta(days=1), 150)
    db_session.add(InvestmentTransaction(
        account_id=account.id, plaid_investment_transaction_id="txn-div-1",
        name="dividend", type="cash", subtype="dividend", amount=-50, date=d0 + timedelta(days=1),
    ))
    db_session.commit()

    flows = external_cash_flows(db_session, [account.id], d0, d0 + timedelta(days=1))
    assert flows == []

    series = build_twr_series(db_session, [account.id], d0, d0 + timedelta(days=1))
    assert len(series) == 2
    assert series[1].growth_index == pytest.approx(1.50, abs=0.001)


def test_twr_reflects_real_gains_without_cash_flows(db_session, account):
    d0 = date(2026, 1, 1)
    _snapshot(db_session, account, d0, 100)
    _snapshot(db_session, account, d0 + timedelta(days=1), 110)
    db_session.commit()

    series = build_twr_series(db_session, [account.id], d0, d0 + timedelta(days=1))
    assert series[-1].growth_index == pytest.approx(1.10, abs=0.001)


def test_build_cagr_annualizes_total_growth():
    from app.services.returns_service import TWRPoint

    series = [
        TWRPoint(date=date(2025, 1, 1), growth_index=1.0),
        TWRPoint(date=date(2026, 1, 1), growth_index=1.10),
    ]
    assert build_cagr(series) == pytest.approx(10.0, abs=0.5)


def test_build_cagr_insufficient_data_returns_none():
    from app.services.returns_service import TWRPoint

    assert build_cagr([TWRPoint(date=date(2026, 1, 1), growth_index=1.0)]) is None


def test_xirr_matches_known_single_period_return(db_session, account):
    d0 = date(2025, 1, 1)
    d1 = date(2026, 1, 1)
    _snapshot(db_session, account, d0, 1000)
    _snapshot(db_session, account, d1, 1100)
    db_session.commit()

    rate = build_mwr_xirr(db_session, [account.id], d0, d1)
    assert rate == pytest.approx(10.0, abs=0.5)


def test_xirr_flips_sign_of_intermediate_cash_flow(db_session, account):
    # $1000 start, a $500 deposit mid-period, $1500 end with zero organic
    # growth beyond the deposit itself. The investor put in 1000 + 500 = 1500
    # total and got back exactly 1500 -> true XIRR is ~0%, regardless of when
    # the deposit landed. A sign bug in how the intermediate flow is folded
    # into the NPV (treating the deposit as money returned to the investor
    # instead of money the investor put in) would instead solve for a large
    # spurious positive rate.
    d0 = date(2025, 1, 1)
    d_mid = date(2025, 7, 1)
    d1 = date(2026, 1, 1)
    _snapshot(db_session, account, d0, 1000)
    _snapshot(db_session, account, d_mid, 1500)
    db_session.add(InvestmentTransaction(
        account_id=account.id, plaid_investment_transaction_id="txn-mid-deposit",
        name="deposit", type="cash", subtype="deposit", amount=-500, date=d_mid,
    ))
    _snapshot(db_session, account, d1, 1500)
    db_session.commit()

    rate = build_mwr_xirr(db_session, [account.id], d0, d1)
    assert rate == pytest.approx(0.0, abs=0.5)


def test_xirr_includes_cash_flow_on_last_snapshot_date(db_session, account):
    # $1000 start, a $100 deposit on the final snapshot date, ending balance
    # $1100 with no organic growth. True XIRR is 0%: the extra $100 is new
    # capital, not a gain. Dropping the last-day flow (the old `< last_date`
    # filter) treats the deposit as a 10% annual return.
    d0 = date(2025, 1, 1)
    d1 = date(2026, 1, 1)
    _snapshot(db_session, account, d0, 1000)
    _snapshot(db_session, account, d1, 1100)
    db_session.add(InvestmentTransaction(
        account_id=account.id, plaid_investment_transaction_id="txn-last-deposit",
        name="deposit", type="cash", subtype="deposit", amount=-100, date=d1,
    ))
    db_session.commit()

    rate = build_mwr_xirr(db_session, [account.id], d0, d1)
    assert rate == pytest.approx(0.0, abs=0.5)


def test_xirr_includes_withdrawal_on_last_snapshot_date(db_session, account):
    # $1000 start, grows to $1100, $100 withdrawn on the last snapshot date
    # leaving $1000. True XIRR is 10% (investor put in 1000, got back 100 +
    # 1000). Dropping the last-day withdrawal would report ~0%.
    d0 = date(2025, 1, 1)
    d1 = date(2026, 1, 1)
    _snapshot(db_session, account, d0, 1000)
    _snapshot(db_session, account, d1, 1000)
    db_session.add(InvestmentTransaction(
        account_id=account.id, plaid_investment_transaction_id="txn-last-withdrawal",
        name="withdrawal", type="cash", subtype="withdrawal", amount=100, date=d1,
    ))
    db_session.commit()

    rate = build_mwr_xirr(db_session, [account.id], d0, d1)
    assert rate == pytest.approx(10.0, abs=0.5)
