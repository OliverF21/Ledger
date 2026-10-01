"""Tests for Plaid enrichment extraction and cash-flow classification."""

from __future__ import annotations

import json

from app.enrichment import apply_enrichment_fields, extract_plaid_enrichment, parse_enrichment_json
from app.txn_classifier import (
    brokerage_cash_flow_kind,
    classify_cash_flow_txn,
    classify_orm_transaction,
    looks_like_brokerage_cashback,
)


def test_extract_plaid_enrichment_keeps_payment_meta_and_codes():
    raw = {
        "name": "ACH WITHDRAWAL ROBINHOOD",
        "merchant_name": "Robinhood",
        "logo_url": "https://example.com/logo.png",
        "payment_channel": "other",
        "original_description": "ACH DEPOSIT BROKERAGE ACCOUNT ENDING 4355",
        "transaction_code": "transfer",
        "payment_meta": {
            "payment_method": "ACH",
            "payee": "Robinhood",
            "payer": None,
            "ppd_id": None,
        },
        "counterparties": [
            {
                "name": "Robinhood",
                "type": "financial_institution",
                "entity_id": "ent_1",
                "website": "https://robinhood.com",
                "confidence_level": "VERY_HIGH",
            }
        ],
        "location": {"city": None, "region": None},
        "personal_finance_category": {
            "primary": "TRANSFER_OUT",
            "detailed": "TRANSFER_OUT_ACCOUNT_TRANSFER",
            "confidence_level": "LOW",
        },
        "personal_finance_category_icon_url": "https://example.com/cat.png",
    }

    parsed = extract_plaid_enrichment(raw)
    assert parsed["original_description"] == "ACH DEPOSIT BROKERAGE ACCOUNT ENDING 4355"
    assert parsed["transaction_code"] == "transfer"
    assert parsed["payment_channel"] == "other"

    extra = json.loads(parsed["enrichment_json"])
    assert extra["payment_meta"] == {"payment_method": "ACH", "payee": "Robinhood"}
    assert extra["counterparties"][0]["type"] == "financial_institution"
    assert "location" not in extra  # empty location dropped


def test_apply_enrichment_fields_sets_new_columns():
    class FakeTxn:
        merchant = None
        category_plaid = None
        category_plaid_detailed = None
        merchant_logo_url = None
        payment_channel = None
        original_description = None
        transaction_code = None
        enrichment_json = None

    txn = FakeTxn()
    apply_enrichment_fields(
        txn,
        {
            "merchant": "Broker",
            "category_plaid": "TRANSFER_OUT",
            "category_plaid_detailed": "TRANSFER_OUT_ACCOUNT_TRANSFER",
            "merchant_logo_url": None,
            "payment_channel": "other",
            "original_description": "ACH BROKERAGE",
            "transaction_code": "transfer",
            "enrichment_json": '{"payment_meta":{"payment_method":"ACH"}}',
        },
    )
    assert txn.original_description == "ACH BROKERAGE"
    assert txn.transaction_code == "transfer"
    assert parse_enrichment_json(txn.enrichment_json)["payment_meta"]["payment_method"] == "ACH"


def test_classifier_marks_brokerage_ach_as_investments():
    role = classify_cash_flow_txn(
        amount=500,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
        merchant="Robinhood",
        original_description="ACH deposit into Brokerage account ending in 4355",
        transaction_code="transfer",
        payment_meta={"payment_method": "ACH"},
        counterparties=[{"name": "Robinhood", "type": "financial_institution"}],
        account_type="depository",
        account_subtype="checking",
    )
    assert role == "investments"


def test_classifier_marks_roth_memo_as_investments():
    role = classify_cash_flow_txn(
        amount=70,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_OTHER_TRANSFER_OUT",
        merchant="ROBINHOOD",
        original_description="ACH DEPOSIT ROTH IRA 3027",
        account_type="depository",
    )
    assert role == "investments"


def test_classifier_keeps_pfc_investment_transfer():
    role = classify_cash_flow_txn(
        amount=250,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS",
        merchant="Vanguard",
        account_type="depository",
    )
    assert role == "investments"


def test_classifier_excludes_credit_card_payment():
    role = classify_cash_flow_txn(
        amount=200,
        category_plaid="LOAN_PAYMENTS",
        category_plaid_detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
        merchant="Robinhood",
        original_description="Payment thank you",
        account_type="depository",
    )
    assert role == "transfer"


def test_classifier_credit_account_purchase_is_spending():
    role = classify_cash_flow_txn(
        amount=42.5,
        category_plaid="GENERAL_MERCHANDISE",
        category_plaid_detailed="GENERAL_MERCHANDISE_ONLINE_MARKETPLACES",
        merchant="Amazon",
        transaction_code="purchase",
        account_type="credit",
        account_subtype="credit card",
    )
    assert role == "spending"


def test_classifier_credit_account_payment_credit_is_transfer():
    role = classify_cash_flow_txn(
        amount=-200,
        category_plaid="TRANSFER_IN",
        category_plaid_detailed="TRANSFER_IN_ACCOUNT_TRANSFER",
        merchant="Payment",
        account_type="credit",
    )
    assert role == "transfer"


def test_classifier_generic_internal_transfer_stays_transfer():
    role = classify_cash_flow_txn(
        amount=100,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
        merchant="Online Transfer",
        original_description="TRANSFER TO CHECKING",
        account_type="depository",
    )
    assert role == "transfer"


def test_matched_transfer_forces_transfer_role_with_no_text_cues():
    # No category, no merchant text cues at all — only the persisted match
    # tells us this is a transfer.
    role = classify_cash_flow_txn(
        amount=500,
        merchant="Unlabeled ACH",
        account_type="depository",
        has_matched_transfer=True,
    )
    assert role == "transfer"


def test_matched_transfer_forces_transfer_role_on_inflow_leg():
    # The receiving leg (e.g. a plain bank-to-bank transfer landing in
    # checking) would otherwise default to "income" with no other signal.
    role = classify_cash_flow_txn(
        amount=-500,
        merchant="Unlabeled ACH",
        account_type="depository",
        has_matched_transfer=True,
    )
    assert role == "transfer"


def test_matched_transfer_outranks_investment_funding_text_heuristic():
    # A Robinhood Gold Card payment's checking-side leg carries the same
    # merchant/ACH/financial_institution text as genuine brokerage funding.
    # "CCB" / Coastal Community Bank is the card bill-pay rail, so the row
    # is a transfer even with no bank-to-bank match. A confirmed match
    # agrees with that.
    matched = classify_cash_flow_txn(
        amount=500,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
        merchant="Robinhood",
        original_description="ACH DEBIT ROBINHOOD CCB",
        transaction_code="transfer",
        payment_meta={"payment_method": "ACH"},
        counterparties=[{"name": "Robinhood", "type": "financial_institution"}],
        account_type="depository",
        account_subtype="checking",
        has_matched_transfer=True,
    )
    assert matched == "transfer"

    unmatched = classify_cash_flow_txn(
        amount=500,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
        merchant="Robinhood",
        original_description="ACH DEBIT ROBINHOOD CCB",
        transaction_code="transfer",
        payment_meta={"payment_method": "ACH"},
        counterparties=[{"name": "Robinhood", "type": "financial_institution"}],
        account_type="depository",
        account_subtype="checking",
        has_matched_transfer=False,
    )
    assert unmatched == "transfer"


def test_gold_card_billpay_is_not_investments_even_when_plaid_says_so():
    # Plaid often files the Robinhood card payment under the brokerage
    # merchant and the investment-transfer detailed category.
    role = classify_cash_flow_txn(
        amount=500,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS",
        merchant="Robinhood",
        original_description="COASTAL COMMUNITY BANK ROBINHOOD",
        transaction_code="transfer",
        payment_meta={"payment_method": "ACH", "payee": "Coastal Community Bank"},
        counterparties=[{"name": "Robinhood", "type": "financial_institution"}],
        account_type="depository",
    )
    assert role == "transfer"


def test_trace_number_457_is_not_a_retirement_plan():
    role = classify_cash_flow_txn(
        amount=80,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
        merchant="Landlord",
        original_description="ACH DEBIT REF 457",
        transaction_code="transfer",
        payment_meta={"payment_method": "ACH"},
        account_type="depository",
    )
    assert role == "transfer"


def test_457b_contribution_is_investments():
    role = classify_cash_flow_txn(
        amount=200,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_OTHER_TRANSFER_OUT",
        merchant="Employer Plan",
        original_description="ACH DEPOSIT 457(b) PLAN",
        account_type="depository",
    )
    assert role == "investments"


def test_zelle_to_person_named_ira_is_not_investments():
    role = classify_cash_flow_txn(
        amount=40,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_TRANSFER_OUT_FROM_APPS",
        merchant="Zelle",
        original_description="ZELLE TO IRA SMITH",
        transaction_code="transfer",
        counterparties=[{"name": "Zelle", "type": "payment_app"}],
        account_type="depository",
    )
    assert role == "transfer"


def test_rent_to_investment_properties_stays_spending():
    role = classify_cash_flow_txn(
        amount=1800,
        category_plaid="RENT_AND_UTILITIES",
        category_plaid_detailed="RENT_AND_UTILITIES_RENT",
        merchant="ABC Investment Properties",
        original_description="ACH RENT ABC INVESTMENT PROPERTIES",
        payment_meta={"payment_method": "ACH"},
        counterparties=[{"name": "First Bank", "type": "financial_institution"}],
        account_type="depository",
    )
    assert role == "spending"


def test_schwab_bank_transfer_is_not_brokerage_funding():
    role = classify_cash_flow_txn(
        amount=300,
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
        merchant="Schwab Bank",
        original_description="ACH TRANSFER SCHWAB BANK",
        transaction_code="transfer",
        payment_meta={"payment_method": "ACH"},
        counterparties=[{"name": "Charles Schwab Bank", "type": "financial_institution"}],
        account_type="depository",
    )
    assert role == "transfer"


def test_manual_override_beats_brokerage_text_heuristic():
    # Custom label (not a PFC spending key) so only the text heuristic could
    # call this investments. transaction_code is omitted so the transfer-code
    # fallback cannot explain the spending result.
    kwargs = dict(
        amount=42,
        category_user="Household",
        category_plaid="TRANSFER_OUT",
        category_plaid_detailed="TRANSFER_OUT_ACCOUNT_TRANSFER",
        merchant="Robinhood",
        original_description="ACH DEBIT ROBINHOOD",
        payment_meta={"payment_method": "ACH"},
        counterparties=[{"name": "Robinhood", "type": "financial_institution"}],
        account_type="depository",
    )
    assert classify_cash_flow_txn(**kwargs, manual_override=True) == "spending"
    assert classify_cash_flow_txn(**kwargs, manual_override=False) == "investments"


def test_matched_investment_does_not_override_a_purchase_category():
    role = classify_cash_flow_txn(
        amount=8.25,
        category_plaid="FOOD_AND_DRINK",
        category_plaid_detailed="FOOD_AND_DRINK_COFFEE",
        merchant="Blue Bottle",
        account_type="depository",
        has_matched_investment=True,
    )
    assert role == "spending"


def test_interest_credit_filed_as_transfer_is_income():
    role = classify_cash_flow_txn(
        amount=-4.5,
        category_plaid="TRANSFER_IN",
        category_plaid_detailed="TRANSFER_IN_ACCOUNT_TRANSFER",
        merchant="Ally Bank",
        original_description="Interest Payment",
        account_type="depository",
        account_subtype="savings",
    )
    assert role == "income"


def test_plaid_interest_earned_is_income():
    role = classify_cash_flow_txn(
        amount=-12.34,
        category_plaid="INCOME",
        category_plaid_detailed="INCOME_INTEREST_EARNED",
        merchant="Savings",
        account_type="depository",
    )
    assert role == "income"


def test_interest_charge_is_not_income():
    role = classify_cash_flow_txn(
        amount=18.2,
        category_plaid="BANK_FEES",
        category_plaid_detailed="BANK_FEES_INTEREST_CHARGE",
        merchant="Interest Charge",
        account_type="credit",
    )
    assert role == "spending"


def test_brokerage_dividend_and_reinvestment_kinds():
    assert brokerage_cash_flow_kind(
        type="cash",
        subtype="dividend",
        name="Cash dividend of $7.68 from SCHD - DIVIDEND",
    ) == "dividend"
    assert brokerage_cash_flow_kind(
        type="cash",
        subtype="qualified dividend",
        name="SCHD",
    ) == "dividend"
    assert brokerage_cash_flow_kind(
        type="cash",
        subtype=None,
        name="Cash dividend of $7.68 from SCHD - DIVIDEND",
    ) == "dividend"
    assert brokerage_cash_flow_kind(
        type="buy",
        subtype="dividend reinvestment",
        name="Dividend reinvestment purchase of 0.233 shares of SCHD for $7.68 total. - DIVIDENDREINVEST",
    ) == "reinvestment"
    assert brokerage_cash_flow_kind(
        type="buy",
        subtype="buy",
        name="Dividend reinvestment purchase of 0.233 shares of SCHD for $7.68 total. - DIVIDENDREINVEST",
    ) == "reinvestment"
    assert brokerage_cash_flow_kind(type="buy", subtype="buy", name="Buy SCHD") is None
    assert brokerage_cash_flow_kind(type="cash", subtype="deposit", name="Deposit") is None
    assert brokerage_cash_flow_kind(
        type="cash",
        subtype="withdrawal",
        name="Dividend cash transferred out",
    ) is None
    assert brokerage_cash_flow_kind(
        type="buy",
        subtype="interest reinvestment",
        name="Interest reinvestment",
    ) is None


def test_cashback_credit_is_income_even_on_a_credit_card():
    role = classify_cash_flow_txn(
        amount=-16.66,
        category_plaid="TRANSFER_IN",
        category_plaid_detailed="TRANSFER_IN_ACCOUNT_TRANSFER",
        merchant="Robinhood",
        original_description="Credit card cashback rewards of $16.66",
        account_type="credit",
    )
    assert role == "income"


def test_card_payment_credit_without_cashback_stays_transfer():
    role = classify_cash_flow_txn(
        amount=-200,
        merchant="Payment thank you",
        account_type="credit",
    )
    assert role == "transfer"


def test_brokerage_cashback_transfer_is_recognized():
    name = (
        "Credit card cashback rewards of $16.66 transferred to "
        "Robinhood Brokerage account ending in 4355. - TRANSFER"
    )
    assert looks_like_brokerage_cashback(type="transfer", subtype="transfer", name=name)
    assert looks_like_brokerage_cashback(type="cash", subtype=None, name=name)
    assert not looks_like_brokerage_cashback(type="buy", subtype="buy", name="Buy Cashback ETF")
    assert not looks_like_brokerage_cashback(type="transfer", subtype="deposit", name="Deposit")


def test_savings_transfer_without_interest_text_stays_out_of_income():
    role = classify_cash_flow_txn(
        amount=-3000,
        category_plaid="TRANSFER_IN",
        category_plaid_detailed="TRANSFER_IN_SAVINGS",
        merchant="Online Transfer",
        account_type="depository",
        account_subtype="savings",
    )
    assert role == "exclude"


def test_matched_investment_forces_investments_role_with_no_text_cues():
    role = classify_cash_flow_txn(
        amount=500,
        merchant="Unlabeled ACH",
        account_type="depository",
        has_matched_investment=True,
    )
    assert role == "investments"


class _FakeAccount:
    def __init__(self, type_=None, subtype=None):
        self.type = type_
        self.subtype = subtype


class _FakeTxn:
    def __init__(self, **kwargs):
        self.amount = kwargs.get("amount")
        self.category_user = kwargs.get("category_user")
        self.category_plaid = kwargs.get("category_plaid")
        self.category_plaid_detailed = kwargs.get("category_plaid_detailed")
        self.merchant = kwargs.get("merchant")
        self.original_description = kwargs.get("original_description")
        self.transaction_code = kwargs.get("transaction_code")
        self.enrichment_json = kwargs.get("enrichment_json")
        self.transfer_match_transaction_id = kwargs.get("transfer_match_transaction_id")
        self.transfer_match_investment_txn_id = kwargs.get("transfer_match_investment_txn_id")


def test_classify_orm_transaction_reads_transfer_match_column():
    txn = _FakeTxn(amount=500, merchant="Robinhood", transfer_match_transaction_id=42)
    role = classify_orm_transaction(txn, account=_FakeAccount(type_="depository"))
    assert role == "transfer"


def test_classify_orm_transaction_reads_investment_match_column():
    txn = _FakeTxn(amount=500, merchant="Robinhood", transfer_match_investment_txn_id=7)
    role = classify_orm_transaction(txn, account=_FakeAccount(type_="depository"))
    assert role == "investments"
