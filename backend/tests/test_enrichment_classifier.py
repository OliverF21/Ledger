"""Tests for Plaid enrichment extraction and cash-flow classification."""

from __future__ import annotations

import json

from app.enrichment import apply_enrichment_fields, extract_plaid_enrichment, parse_enrichment_json
from app.txn_classifier import classify_cash_flow_txn


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
        original_description="TRANSFER TO SAVINGS",
        account_type="depository",
    )
    assert role == "transfer"
