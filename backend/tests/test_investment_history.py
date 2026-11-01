from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import (  # noqa: E402
    Account,
    BalanceSnapshot,
    Base,
    Holding,
    InvestmentTransaction,
    Item,
    MarketPrice,
    Security,
    User,
)
from app.services.investment_service import (  # noqa: E402
    _build_investment_history,
    _history_change,
    _portfolio_period_change,
    investment_net_equity_total,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _brokerage(db, *, balance: str = "2000"):
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db.add(item)
    db.flush()
    account = Account(
        item_id=item.id,
        plaid_account_id="acc-1",
        name="Brokerage",
        type="investment",
        current_balance=Decimal(balance),
    )
    db.add(account)
    db.flush()
    return account


def test_short_snapshots_period_change_differs_for_6m_vs_1y(db_session):
    """Plaid has no historical balances — snapshots only exist since first sync.
    Period change for 6M vs 1Y must still differ by marking current holdings
    to market over the selected window."""
    account = _brokerage(db_session, balance="2000")
    sec = Security(plaid_security_id="sec-A", ticker_symbol="TICKA", type="equity")
    db_session.add(sec)
    db_session.flush()
    db_session.add(
        Holding(
            account_id=account.id,
            security_id=sec.id,
            quantity=Decimal("10"),
            institution_price=Decimal("200"),
            institution_value=Decimal("2000"),
        )
    )

    today = date.today()
    for days_ago in range(400, -1, -1):
        day = today - timedelta(days=days_ago)
        db_session.add(
            MarketPrice(
                ticker="TICKA",
                price_date=day,
                close_price=Decimal(str(100 + (400 - days_ago) * 0.25)),
            )
        )

    # Only a few weeks of actual account snapshots, same span for any months=.
    for days_ago in range(20, -1, -1):
        db_session.add(
            BalanceSnapshot(
                account_id=account.id,
                balance=Decimal("2000"),
                snapshot_date=today - timedelta(days=days_ago),
            )
        )
    db_session.commit()

    live = investment_net_equity_total([account])
    six, _ = _build_investment_history(db_session, account_ids=[account.id], months=6, live_total=live)
    twelve, _ = _build_investment_history(db_session, account_ids=[account.id], months=12, live_total=live)

    six_change, _ = _history_change(six)
    twelve_change, _ = _history_change(twelve)

    assert twelve_change != six_change
    # Longer window of a steadily rising book must show a larger dollar change.
    assert abs(twelve_change) > abs(six_change)


def test_full_snapshot_coverage_keeps_using_balances(db_session):
    """When snapshots already span the window, don't replace them with MTM."""
    account = _brokerage(db_session, balance="120")
    today = date.today()
    for days_ago in range(400, -1, -1):
        db_session.add(
            BalanceSnapshot(
                account_id=account.id,
                balance=Decimal(str(100 + (400 - days_ago))),
                snapshot_date=today - timedelta(days=days_ago),
            )
        )
    db_session.commit()

    history, from_snapshots = _build_investment_history(
        db_session, account_ids=[account.id], months=6, live_total=120.0
    )
    assert from_snapshots is True
    # First point is the snapshot on the 6-month cutoff (1st of that month),
    # not a reconstructed price series.
    cutoff_year = today.year - (6 // 12)
    cutoff_month = today.month - (6 % 12)
    if cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1
    cutoff = date(cutoff_year, cutoff_month, 1)
    assert history[0].date == str(cutoff)
    assert history[0].total == pytest.approx(100 + (cutoff - (today - timedelta(days=400))).days)


def test_snapshot_return_excludes_deposits(db_session):
    """A deposit raises portfolio value. It is not a capital gain."""
    account = _brokerage(db_session, balance="2100")
    today = date.today()
    mid = today - timedelta(days=40)
    for days_ago in range(400, -1, -1):
        day = today - timedelta(days=days_ago)
        db_session.add(
            BalanceSnapshot(
                account_id=account.id,
                balance=Decimal("1000" if day < mid else "2100"),
                snapshot_date=day,
            )
        )
    db_session.add(
        InvestmentTransaction(
            account_id=account.id,
            plaid_investment_transaction_id="dep-1",
            name="deposit",
            type="cash",
            subtype="deposit",
            amount=Decimal("-1000"),
            date=mid,
        )
    )
    db_session.commit()

    history, from_snapshots = _build_investment_history(
        db_session, account_ids=[account.id], months=6, live_total=2100.0
    )
    assert from_snapshots is True
    amount, pct = _portfolio_period_change(
        db_session,
        [account.id],
        history,
        from_balance_snapshots=True,
    )
    assert amount == pytest.approx(100.0, abs=0.05)
    assert pct == pytest.approx(10.0, abs=0.05)
    # The raw balance change still includes the deposit. The displayed return must not.
    assert history[-1].total - history[0].total == pytest.approx(1100.0, abs=0.05)


def test_snapshot_return_keeps_dividends(db_session):
    account = _brokerage(db_session, balance="1100")
    today = date.today()
    payday = today - timedelta(days=20)
    for days_ago in range(400, -1, -1):
        day = today - timedelta(days=days_ago)
        db_session.add(
            BalanceSnapshot(
                account_id=account.id,
                balance=Decimal("1000" if day < payday else "1100"),
                snapshot_date=day,
            )
        )
    db_session.add(
        InvestmentTransaction(
            account_id=account.id,
            plaid_investment_transaction_id="div-1",
            name="dividend",
            type="cash",
            subtype="dividend",
            amount=Decimal("-100"),
            date=payday,
        )
    )
    db_session.commit()

    history, from_snapshots = _build_investment_history(
        db_session, account_ids=[account.id], months=6, live_total=1100.0
    )
    assert from_snapshots is True
    amount, pct = _portfolio_period_change(
        db_session,
        [account.id],
        history,
        from_balance_snapshots=True,
    )
    assert amount == pytest.approx(100.0, abs=0.05)
    assert pct == pytest.approx(10.0, abs=0.05)


def test_mark_to_market_return_does_not_subtract_deposits(db_session):
    """Mark-to-market history never includes the deposit, so subtracting it
    would turn a price gain into a fake loss."""
    account = _brokerage(db_session, balance="2000")
    sec = Security(plaid_security_id="sec-B", ticker_symbol="TICKB", type="equity")
    db_session.add(sec)
    db_session.flush()
    db_session.add(
        Holding(
            account_id=account.id,
            security_id=sec.id,
            quantity=Decimal("10"),
            institution_price=Decimal("200"),
            institution_value=Decimal("2000"),
        )
    )
    today = date.today()
    for days_ago in range(400, -1, -1):
        day = today - timedelta(days=days_ago)
        db_session.add(
            MarketPrice(
                ticker="TICKB",
                price_date=day,
                close_price=Decimal(str(100 + (400 - days_ago) * 0.25)),
            )
        )
    for days_ago in range(20, -1, -1):
        db_session.add(
            BalanceSnapshot(
                account_id=account.id,
                balance=Decimal("2000"),
                snapshot_date=today - timedelta(days=days_ago),
            )
        )
    db_session.add(
        InvestmentTransaction(
            account_id=account.id,
            plaid_investment_transaction_id="dep-mtm",
            name="deposit",
            type="cash",
            subtype="deposit",
            amount=Decimal("-50000"),
            date=today - timedelta(days=10),
        )
    )
    db_session.commit()

    history, from_snapshots = _build_investment_history(
        db_session, account_ids=[account.id], months=6, live_total=2000.0
    )
    assert from_snapshots is False
    amount, _pct = _portfolio_period_change(
        db_session,
        [account.id],
        history,
        from_balance_snapshots=False,
    )
    assert amount == pytest.approx(history[-1].total - history[0].total, abs=0.02)
    assert abs(amount) < 10000
