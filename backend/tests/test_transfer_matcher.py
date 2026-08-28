"""Tests for cross-account transfer matching (app.transfer_matcher)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import InvestmentTransaction, Transaction
from app.transfer_matcher import match_transfers


@pytest.fixture(autouse=True)
def mock_date():
    """Mock date.today() to return a date that makes test dates fall within the lookback window."""
    from unittest.mock import MagicMock

    mock_date_class = MagicMock(wraps=date)
    mock_date_class.today.return_value = date(2026, 8, 24)

    with patch.dict('app.transfer_matcher.__dict__', {'date': mock_date_class}):
        yield


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _txn(**overrides) -> Transaction:
    defaults = dict(
        account_id=1,
        merchant="Test",
        amount=100.0,
        date=date(2026, 8, 14),
        pending=False,
        removed=False,
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def _investment_txn(**overrides) -> InvestmentTransaction:
    defaults = dict(
        account_id=3,
        plaid_investment_transaction_id="itx_default",
        name="ACH deposit",
        type="cash",
        subtype="deposit",
        amount=-100.0,
        date=date(2026, 8, 14),
    )
    defaults.update(overrides)
    return InvestmentTransaction(**defaults)


def test_matches_transaction_to_transaction_pair_exact_amount(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 15))
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    db.refresh(card_in)
    assert checking_out.transfer_match_transaction_id == card_in.id
    assert card_in.transfer_match_transaction_id == checking_out.id
    assert checking_out.transfer_match_investment_txn_id is None


def test_matches_transaction_to_investment_cash_deposit(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    deposit = _investment_txn(
        account_id=3, amount=-500.0, date=date(2026, 8, 16), plaid_investment_transaction_id="itx_1"
    )
    db.add_all([checking_out, deposit])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    db.refresh(deposit)
    assert checking_out.transfer_match_investment_txn_id == deposit.id
    assert checking_out.transfer_match_transaction_id is None
    assert deposit.matched_transaction_id == checking_out.id


def test_amount_within_tolerance_still_matches(db):
    # $500 outflow vs $497 inflow: $3 diff, under the $5 floor tolerance.
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    card_in = _txn(account_id=2, amount=-497.0, date=date(2026, 8, 14))
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == card_in.id


def test_amount_outside_tolerance_does_not_match(db):
    # $500 vs $480: $20 diff exceeds both the $5 floor and 1% of $500 ($5).
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    unrelated = _txn(account_id=2, amount=-480.0, date=date(2026, 8, 14))
    db.add_all([checking_out, unrelated])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id is None


def test_date_outside_window_does_not_match(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 19))  # 5 days later
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id is None


def test_prefers_transaction_match_over_investment_match(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 14))
    deposit = _investment_txn(
        account_id=3, amount=-500.0, date=date(2026, 8, 14), plaid_investment_transaction_id="itx_2"
    )
    db.add_all([checking_out, card_in, deposit])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == card_in.id
    assert checking_out.transfer_match_investment_txn_id is None


def test_rerun_is_idempotent_and_does_not_rematch(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 14))
    db.add_all([checking_out, card_in])
    db.commit()

    first = match_transfers(db)
    second = match_transfers(db)

    assert first == {"transfer_pairs": 1, "investment_pairs": 0}
    assert second == {"transfer_pairs": 0, "investment_pairs": 0}


def test_pending_transactions_excluded(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14), pending=True)
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 14))
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id is None


def test_same_account_transactions_never_match(db):
    txn_a = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    txn_b = _txn(account_id=1, amount=-500.0, date=date(2026, 8, 14))
    db.add_all([txn_a, txn_b])
    db.commit()

    match_transfers(db)

    db.refresh(txn_a)
    assert txn_a.transfer_match_transaction_id is None


def test_dividend_cash_row_excluded_from_investment_candidates(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    dividend = _investment_txn(
        account_id=3,
        amount=-500.0,
        date=date(2026, 8, 14),
        subtype="dividend",
        plaid_investment_transaction_id="itx_3",
    )
    db.add_all([checking_out, dividend])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    assert checking_out.transfer_match_investment_txn_id is None


def test_tie_break_prefers_closer_amount_over_closer_date(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    # $2 off, 2 days off — smaller amount diff than closer_date below.
    closer_amount = _txn(account_id=2, amount=-498.0, date=date(2026, 8, 16))
    # exact date, but $5 off — larger amount diff, so it should lose.
    closer_date = _txn(account_id=2, amount=-495.0, date=date(2026, 8, 14))
    db.add_all([checking_out, closer_amount, closer_date])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == closer_amount.id


def test_tie_break_prefers_closer_date_when_amounts_tie(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    # Both exact-amount matches; only the date differs.
    farther_date = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 17))
    closer_date = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 15))
    db.add_all([checking_out, farther_date, closer_date])
    db.commit()

    match_transfers(db)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == closer_date.id
