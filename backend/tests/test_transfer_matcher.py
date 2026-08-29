"""Tests for cross-account transfer matching (app.transfer_matcher)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import InvestmentTransaction, Transaction
from app.transfer_matcher import match_transfers

# Pinned "today" injected into every match_transfers() call so the fixture
# dates below (2026-08-14 .. 2026-08-19) stay inside the 10-day default
# lookback window without mocking date.today().
TODAY = date(2026, 8, 24)


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
    # transaction_code="transfer" by default so fixtures clear the
    # transfer-plausibility precondition: these tests are about whether
    # amount/date/tie-break logic works for legs that are already plausibly
    # transfers. Tests of the precondition itself override it to None.
    defaults = dict(
        account_id=1,
        merchant="Test",
        amount=100.0,
        date=date(2026, 8, 14),
        pending=False,
        removed=False,
        hidden=False,
        transaction_code="transfer",
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

    match_transfers(db, today=TODAY)

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

    match_transfers(db, today=TODAY)

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

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == card_in.id


def test_amount_outside_tolerance_does_not_match(db):
    # $500 vs $480: $20 diff exceeds both the $5 floor and 1% of $500 ($5).
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    unrelated = _txn(account_id=2, amount=-480.0, date=date(2026, 8, 14))
    db.add_all([checking_out, unrelated])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id is None


def test_date_outside_window_does_not_match(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 19))  # 5 days later
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db, today=TODAY)

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

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == card_in.id
    assert checking_out.transfer_match_investment_txn_id is None


def test_rerun_is_idempotent_and_does_not_rematch(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 14))
    db.add_all([checking_out, card_in])
    db.commit()

    first = match_transfers(db, today=TODAY)
    second = match_transfers(db, today=TODAY)

    assert first == {"transfer_pairs": 1, "investment_pairs": 0}
    assert second == {"transfer_pairs": 0, "investment_pairs": 0}


def test_pending_transactions_excluded(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14), pending=True)
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 14))
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id is None


def test_same_account_transactions_never_match(db):
    txn_a = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    txn_b = _txn(account_id=1, amount=-500.0, date=date(2026, 8, 14))
    db.add_all([txn_a, txn_b])
    db.commit()

    match_transfers(db, today=TODAY)

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

    match_transfers(db, today=TODAY)

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

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == closer_amount.id


def test_tolerance_uses_larger_leg_not_scanned_leg(db):
    # Regression test for the tolerance-base bug: _within_tolerance used to
    # compute `max($5, 1% of amount_a)` where amount_a is whichever bank
    # Transaction the outer loop in match_transfers happens to be scanning
    # (here, checking_out — inserted first, so it gets the lower id and is
    # visited first per the `.order_by(date.asc(), id.asc())` ordering).
    # That under-tolerates whenever the scanned leg is the SMALLER of the two
    # amounts, contradicting the spec: "max($5, 1% of the larger leg's
    # amount)".
    #
    # Let S = 10000 (scanned/smaller leg), L = 10101 (counterparty/larger
    # leg). diff = |S - L| = 101.
    #   Old (buggy) tolerance = max(5, 0.01 * S) = max(5, 100) = 100
    #     -> diff (101) > 100 -> OLD CODE REJECTS THE MATCH.
    #   New (fixed) tolerance = max(5, 0.01 * max(S, L)) = max(5, 101.01) = 101.01
    #     -> diff (101) <= 101.01 -> NEW CODE ACCEPTS THE MATCH.
    checking_out = _txn(account_id=1, amount=10000.0, date=date(2026, 8, 14))
    counterparty = _txn(account_id=2, amount=-10101.0, date=date(2026, 8, 14))
    db.add_all([checking_out, counterparty])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == counterparty.id


def test_investment_subtype_matched_despite_case_and_whitespace(db):
    # Regression test: the SQL filter used to compare
    # InvestmentTransaction.subtype.in_(EXTERNAL_CASH_FLOW_SUBTYPES) directly,
    # which is case/whitespace-sensitive and silently excluded any row whose
    # subtype wasn't already lowercased/trimmed exactly like the constant set
    # (e.g. Plaid returning "Deposit" instead of "deposit"). The fix filters
    # by `type` in SQL but normalizes `subtype` in Python — mirroring
    # app.services.returns_service.external_cash_flows's
    # `(t.subtype or "").strip().lower() in EXTERNAL_CASH_FLOW_SUBTYPES` — so
    # this mixed-case, whitespace-padded subtype must still match.
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    deposit = _investment_txn(
        account_id=3,
        amount=-500.0,
        date=date(2026, 8, 14),
        subtype=" Deposit ",
        plaid_investment_transaction_id="itx_case",
    )
    db.add_all([checking_out, deposit])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    db.refresh(deposit)
    assert checking_out.transfer_match_investment_txn_id == deposit.id
    assert deposit.matched_transaction_id == checking_out.id


def test_tie_break_prefers_closer_date_when_amounts_tie(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    # Both exact-amount matches; only the date differs.
    farther_date = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 17))
    closer_date = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 15))
    db.add_all([checking_out, farther_date, closer_date])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == closer_date.id


def test_non_transferish_small_amounts_do_not_match(db):
    # Regression test for the missing plausibility guard: an $8.25 coffee on
    # one account and an unrelated $4.10 refund on another, 3 days apart, have
    # a $4.15 diff — inside the flat $5 tolerance floor. Without the
    # transfer-plausibility precondition they were paired and BOTH permanently
    # reclassified out of spending/income (the matcher never revisits a pair).
    coffee = _txn(
        account_id=1,
        amount=8.25,
        date=date(2026, 8, 14),
        merchant="Blue Bottle",
        category_plaid="FOOD_AND_DRINK",
        category_plaid_detailed="FOOD_AND_DRINK_COFFEE",
        transaction_code=None,
    )
    refund = _txn(
        account_id=2,
        amount=-4.10,
        date=date(2026, 8, 17),
        merchant="Target",
        category_plaid="GENERAL_MERCHANDISE",
        category_plaid_detailed="GENERAL_MERCHANDISE_OTHER",
        transaction_code=None,
    )
    db.add_all([coffee, refund])
    db.commit()

    stats = match_transfers(db, today=TODAY)

    db.refresh(coffee)
    db.refresh(refund)
    assert coffee.transfer_match_transaction_id is None
    assert refund.transfer_match_transaction_id is None
    assert stats == {"transfer_pairs": 0, "investment_pairs": 0}


def test_one_transferish_leg_is_enough_to_match(db):
    # The precondition needs only ONE leg to carry a Plaid transfer signal:
    # here the counterpart has no transaction_code, but a TRANSFER_ category.
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14), transaction_code=None)
    card_in = _txn(
        account_id=2,
        amount=-500.0,
        date=date(2026, 8, 14),
        transaction_code=None,
        category_plaid="TRANSFER_IN",
        category_plaid_detailed="TRANSFER_IN_ACCOUNT_TRANSFER",
    )
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == card_in.id


def test_loan_payment_category_satisfies_the_precondition(db):
    checking_out = _txn(
        account_id=1,
        amount=500.0,
        date=date(2026, 8, 14),
        transaction_code=None,
        category_plaid="LOAN_PAYMENTS",
        category_plaid_detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
    )
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 14), transaction_code=None)
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_transaction_id == card_in.id


def test_investment_match_does_not_require_a_transferish_bank_leg(db):
    # The precondition is bank<->bank only; the investment pool is already
    # restricted to external cash-flow types/subtypes.
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14), transaction_code=None)
    deposit = _investment_txn(
        account_id=3, amount=-500.0, date=date(2026, 8, 14), plaid_investment_transaction_id="itx_notc"
    )
    db.add_all([checking_out, deposit])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    assert checking_out.transfer_match_investment_txn_id == deposit.id


def test_hidden_transactions_excluded(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14), hidden=True)
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 14))
    db.add_all([checking_out, card_in])
    db.commit()

    match_transfers(db, today=TODAY)

    db.refresh(checking_out)
    db.refresh(card_in)
    assert checking_out.transfer_match_transaction_id is None
    assert card_in.transfer_match_transaction_id is None


def test_dry_run_reports_matches_without_persisting(db):
    checking_out = _txn(account_id=1, amount=500.0, date=date(2026, 8, 14))
    card_in = _txn(account_id=2, amount=-500.0, date=date(2026, 8, 14))
    db.add_all([checking_out, card_in])
    db.commit()

    stats = match_transfers(db, today=TODAY, dry_run=True)

    assert stats == {"transfer_pairs": 1, "investment_pairs": 0, "dry_run": True}

    # Nothing committed: expire the in-session state and re-read from the DB.
    db.rollback()
    db.expire_all()
    assert db.get(Transaction, checking_out.id).transfer_match_transaction_id is None
    assert db.get(Transaction, card_in.id).transfer_match_transaction_id is None

    # And a real run afterwards still finds the same pair.
    assert match_transfers(db, today=TODAY) == {"transfer_pairs": 1, "investment_pairs": 0}
