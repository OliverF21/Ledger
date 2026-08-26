"""Tests for the merchant/description categorization rules engine."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.categorization import (
    apply_rule_to_existing_transactions,
    apply_rules_to_transaction,
    match_rule,
    revert_deleted_rule_from_existing_transactions,
    rule_matches,
)
from app.database import Base
from app.models import CategoryRule, Transaction


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


def _make_txn(**overrides):
    defaults = dict(
        account_id=1,
        merchant="Robinhood",
        amount=100.0,
        date=date(2026, 8, 14),
        original_description=None,
        category_user=None,
        manual_override=False,
        removed=False,
        hidden=False,
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def _rule(merchant_pattern: str, description_pattern: str | None = None) -> CategoryRule:
    return CategoryRule(user_id=1, category_id=1, merchant_pattern=merchant_pattern, description_pattern=description_pattern)


class TestRuleMatches:
    def test_merchant_only_rule_ignores_description(self):
        rule = _rule("Robinhood")
        assert rule_matches("Robinhood", "anything at all", rule)
        assert rule_matches("Robinhood", "", rule)

    def test_merchant_mismatch_fails_regardless_of_description(self):
        rule = _rule("Starbucks", description_pattern="CCB")
        assert not rule_matches("Robinhood", "Robinhood CCB", rule)

    def test_description_pattern_requires_both_to_match(self):
        rule = _rule("Robinhood", description_pattern="CCB|Coastal Community Bank")
        assert rule_matches("Robinhood", "Robinhood CCB", rule)
        assert rule_matches("Robinhood", "COASTAL COMMUNITY BANK VIA ROBINHOOD", rule)

    def test_description_pattern_rejects_merchant_match_with_no_description_match(self):
        """The exact bug: a bare brokerage transfer must NOT match the card-payment rule."""
        rule = _rule("Robinhood", description_pattern="CCB|Coastal Community Bank")
        assert not rule_matches("Robinhood", "ROBINHOOD", rule)
        assert not rule_matches("Robinhood", "ACH DEPOSIT ROTH IRA 3027", rule)


class TestMatchRule:
    def test_first_matching_rule_wins(self):
        rules = [
            (_rule("Robinhood", description_pattern="CCB"), "Credit Card Payment"),
            (_rule("Robinhood"), "Investment / Retirement Transfer Out"),
        ]
        assert match_rule("Robinhood", "Robinhood CCB", rules) == "Credit Card Payment"
        assert match_rule("Robinhood", "ROBINHOOD", rules) == "Investment / Retirement Transfer Out"

    def test_no_match_returns_none(self):
        rules = [(_rule("Starbucks"), "Dining Out")]
        assert match_rule("Robinhood", "Robinhood CCB", rules) is None


class TestApplyRulesToTransaction:
    def test_two_field_rule_categorizes_card_funding_transfer(self):
        rules = [(_rule("Robinhood", description_pattern="CCB|Coastal Community Bank"), "Credit Card Payment")]
        txn = _make_txn(original_description="Robinhood CCB")
        apply_rules_to_transaction(txn, rules)
        assert txn.category_user == "Credit Card Payment"

    def test_two_field_rule_skips_genuine_investment_transfer(self):
        rules = [(_rule("Robinhood", description_pattern="CCB|Coastal Community Bank"), "Credit Card Payment")]
        txn = _make_txn(original_description="ACH DEPOSIT ROTH IRA 3027")
        apply_rules_to_transaction(txn, rules)
        assert txn.category_user is None

    def test_manual_override_is_never_touched(self):
        rules = [(_rule("Robinhood", description_pattern="CCB"), "Credit Card Payment")]
        txn = _make_txn(original_description="Robinhood CCB", category_user="Something Else", manual_override=True)
        apply_rules_to_transaction(txn, rules)
        assert txn.category_user == "Something Else"

    def test_merchant_only_rule_unaffected_by_new_field(self):
        rules = [(_rule("Starbucks"), "Dining Out")]
        txn = _make_txn(merchant="Starbucks", original_description=None)
        apply_rules_to_transaction(txn, rules)
        assert txn.category_user == "Dining Out"


class TestApplyRuleToExistingTransactions:
    def test_backfill_only_matches_card_funding_rows(self, db):
        card_txn = _make_txn(merchant="Robinhood", original_description="Robinhood CCB")
        investment_txn = _make_txn(merchant="Robinhood", original_description="ACH DEPOSIT ROTH IRA 3027")
        db.add_all([card_txn, investment_txn])
        db.commit()

        applied = apply_rule_to_existing_transactions(
            db, "Robinhood", "Credit Card Payment", description_pattern="CCB|Coastal Community Bank"
        )
        db.commit()

        assert applied == 1
        assert db.get(Transaction, card_txn.id).category_user == "Credit Card Payment"
        assert db.get(Transaction, investment_txn.id).category_user is None

    def test_backfill_skips_manual_override(self, db):
        txn = _make_txn(
            merchant="Robinhood",
            original_description="Robinhood CCB",
            category_user="Kept As Is",
            manual_override=True,
        )
        db.add(txn)
        db.commit()

        applied = apply_rule_to_existing_transactions(
            db, "Robinhood", "Credit Card Payment", description_pattern="CCB"
        )
        db.commit()

        assert applied == 0
        assert db.get(Transaction, txn.id).category_user == "Kept As Is"

    def test_merchant_only_backfill_unaffected(self, db):
        txn = _make_txn(merchant="Starbucks", original_description=None)
        db.add(txn)
        db.commit()

        applied = apply_rule_to_existing_transactions(db, "Starbucks", "Dining Out")
        db.commit()

        assert applied == 1
        assert db.get(Transaction, txn.id).category_user == "Dining Out"


class TestRevertDeletedRuleFromExistingTransactions:
    def test_revert_respects_description_pattern_on_deleted_rule(self, db):
        card_txn = _make_txn(
            merchant="Robinhood", original_description="Robinhood CCB", category_user="Credit Card Payment"
        )
        investment_txn = _make_txn(
            merchant="Robinhood", original_description="ROBINHOOD", category_user="Investments"
        )
        db.add_all([card_txn, investment_txn])
        db.commit()

        reverted = revert_deleted_rule_from_existing_transactions(
            db,
            merchant_pattern="Robinhood",
            remaining_rules=[],
            description_pattern="CCB|Coastal Community Bank",
        )
        db.commit()

        assert reverted == 1
        assert db.get(Transaction, card_txn.id).category_user is None
        # Not touched: didn't match the deleted rule's description_pattern in the first place.
        assert db.get(Transaction, investment_txn.id).category_user == "Investments"
