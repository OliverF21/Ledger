"""
Cash-flow transaction role classifier.

Uses Plaid PFC categories plus account type and richer sync fields
(original_description, payment_meta, counterparties, transaction_code) to
tell spending apart from neutral transfers and investment funding.

Kept institution-agnostic: looks for brokerage/retirement/ACH transfer cues,
not a specific broker name.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from app.analytics_shared import (
    TRANSFER_OUT_SPENDING_SUBCATEGORIES,
    _exclusion_key,
    category_key_for_spending_rules,
    is_excluded_from_income,
    is_excluded_from_spending,
)

CashFlowRole = Literal["income", "spending", "investments", "transfer", "exclude"]

# Generic funding / retirement cues in bank memos and payment_meta.
_INVESTMENT_TEXT = re.compile(
    r"\b("
    r"brokerage|retirement|roth|ira|401[\s\-]?k|403[\s\-]?b|457\b|"
    r"pension|hsa\b|investment|securities|mutual\s+fund|etf\b|"
    r"wealthfront|betterment|vanguard|fidelity|schwab|etrade|e[\s\-]?trade|"
    r"robinhood|coinbase|kraken"
    r")\b",
    re.IGNORECASE,
)
_ACH_TEXT = re.compile(r"\bach\b", re.IGNORECASE)
_PAYMENT_TEXT = re.compile(
    r"\b(payment|autopay|auto[\s\-]?pay|thank\s+you|credit\s+card)\b",
    re.IGNORECASE,
)


def _text_blob(*parts: str | None) -> str:
    return " ".join(p for p in parts if p).strip()


def _payment_meta_blob(payment_meta: dict[str, Any] | None) -> str:
    if not payment_meta:
        return ""
    return _text_blob(
        *(str(v) for v in payment_meta.values() if v is not None and v != "")
    )


def _has_financial_institution_counterparty(counterparties: list[dict[str, Any]] | None) -> bool:
    if not counterparties:
        return False
    for c in counterparties:
        ctype = str(c.get("type") or "").lower()
        if ctype in {"financial_institution", "payment_app"}:
            return True
    return False


def _looks_like_investment_funding(
    *,
    merchant: str | None,
    original_description: str | None,
    description_raw: str | None,
    payment_meta: dict[str, Any] | None,
    counterparties: list[dict[str, Any]] | None,
    transaction_code: str | None,
    category_key: str,
) -> bool:
    if category_key in TRANSFER_OUT_SPENDING_SUBCATEGORIES:
        return True

    blob = _text_blob(
        merchant,
        original_description,
        description_raw,
        _payment_meta_blob(payment_meta),
    )
    if _INVESTMENT_TEXT.search(blob):
        # ACH + brokerage/retirement memo is a strong funding signal.
        if _ACH_TEXT.search(blob) or _has_financial_institution_counterparty(counterparties):
            return True
        if (transaction_code or "").lower() == "transfer":
            return True
        # Even without ACH, a clear retirement/brokerage memo on a transfer-like
        # category is enough.
        if category_key.startswith("TRANSFER_OUT") or category_key == "TRANSFER":
            return True
        if _has_financial_institution_counterparty(counterparties):
            return True

    method = str((payment_meta or {}).get("payment_method") or "").lower()
    if method in {"ach", "wire"} and _INVESTMENT_TEXT.search(blob):
        return True

    return False


def _looks_like_card_payment(
    *,
    account_type: str | None,
    amount: float,
    merchant: str | None,
    original_description: str | None,
    description_raw: str | None,
    category_key: str,
) -> bool:
    if category_key.startswith("LOAN_PAYMENTS"):
        return True
    # Credit-side payment posting on the card account (money moving onto the card).
    if (account_type or "").lower() == "credit" and amount < 0:
        return True
    blob = _text_blob(merchant, original_description, description_raw)
    if (account_type or "").lower() == "credit" and _PAYMENT_TEXT.search(blob):
        return True
    return False


def classify_cash_flow_txn(
    *,
    amount: float,
    category_user: str | None = None,
    category_plaid: str | None = None,
    category_plaid_detailed: str | None = None,
    merchant: str | None = None,
    original_description: str | None = None,
    description_raw: str | None = None,
    transaction_code: str | None = None,
    payment_meta: dict[str, Any] | None = None,
    counterparties: list[dict[str, Any]] | None = None,
    account_type: str | None = None,
    account_subtype: str | None = None,
) -> CashFlowRole:
    """
    Classify a transaction for Cash Flow.

    Returns:
      income / spending / investments / transfer / exclude
    """
    del account_subtype  # reserved for finer heuristics later
    amount = float(amount)
    category_key = _exclusion_key(
        category_key_for_spending_rules(category_user, category_plaid, category_plaid_detailed)
    )

    if amount < 0:
        if _looks_like_card_payment(
            account_type=account_type,
            amount=amount,
            merchant=merchant,
            original_description=original_description,
            description_raw=description_raw,
            category_key=category_key,
        ):
            return "transfer"
        if is_excluded_from_income(category_key):
            return "exclude"
        return "income"

    # Outflows (amount > 0)
    if _looks_like_card_payment(
        account_type=account_type,
        amount=amount,
        merchant=merchant,
        original_description=original_description,
        description_raw=description_raw,
        category_key=category_key,
    ):
        return "transfer"

    if _looks_like_investment_funding(
        merchant=merchant,
        original_description=original_description,
        description_raw=description_raw,
        payment_meta=payment_meta,
        counterparties=counterparties,
        transaction_code=transaction_code,
        category_key=category_key,
    ):
        return "investments"

    if is_excluded_from_spending(category_key):
        return "transfer"

    # Credit-card purchases on a credit account are real spending.
    if (account_type or "").lower() == "credit":
        return "spending"

    if (transaction_code or "").lower() == "transfer":
        # Unclassified transfer code with no investment cues → neutral transfer.
        return "transfer"

    return "spending"


def classify_orm_transaction(txn: Any, account: Any | None = None) -> CashFlowRole:
    """Convenience wrapper for SQLAlchemy Transaction (+ optional Account)."""
    from app.enrichment import parse_enrichment_json

    acct = account if account is not None else getattr(txn, "account", None)
    extra = parse_enrichment_json(getattr(txn, "enrichment_json", None)) or {}
    return classify_cash_flow_txn(
        amount=float(txn.amount),
        category_user=txn.category_user,
        category_plaid=txn.category_plaid,
        category_plaid_detailed=txn.category_plaid_detailed,
        merchant=txn.merchant,
        original_description=getattr(txn, "original_description", None),
        description_raw=extra.get("description_raw"),
        transaction_code=getattr(txn, "transaction_code", None),
        payment_meta=extra.get("payment_meta"),
        counterparties=extra.get("counterparties"),
        account_type=getattr(acct, "type", None) if acct is not None else None,
        account_subtype=getattr(acct, "subtype", None) if acct is not None else None,
    )
