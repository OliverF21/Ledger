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
    resolve_category_to_pfc_key,
)

CashFlowRole = Literal["income", "spending", "investments", "savings", "transfer", "exclude"]

# Plaid primaries that are purchases, bills, and fees. A keyword in the memo
# must not pull these into Investments — "ABC Investment Properties" rent and
# a Fidelity debit-card purchase are still spending.
_CONSUMPTIVE_PRIMARIES = (
    "BANK_FEES",
    "ENTERTAINMENT",
    "FOOD_AND_DRINK",
    "GENERAL_MERCHANDISE",
    "HOME_IMPROVEMENT",
    "MEDICAL",
    "PERSONAL_CARE",
    "GENERAL_SERVICES",
    "GOVERNMENT_AND_NON_PROFIT",
    "TRANSPORTATION",
    "TRAVEL",
    "RENT_AND_UTILITIES",
    "SHOPPING",
    "EDUCATION",
    "PETS",
    "OTHER",
)

# Funding / retirement cues. Short ambiguous tokens are intentionally narrow:
# bare "ira" matches the first name Ira, bare "457" matches trace numbers,
# and bare "investment" matches property managers.
_INVESTMENT_TEXT = re.compile(
    r"(?<!\w)(?:"
    r"brokerage|retirement|"
    r"roth\s+ira|traditional\s+ira|sep\s+ira|simple\s+ira|"
    r"ira\s+(?:contribution|deposit|transfer|account|funding)|"
    r"401[\s\-]?k|403[\s\-]?b|457(?:[\s\-]?b|\s*\(\s*b\s*\))|"
    r"pension|hsa|"
    r"investment\s+(?:account|acct|transfer|deposit|contribution|funding|portfolio)|"
    r"securities|mutual\s+fund|etf|"
    r"wealthfront|betterment|vanguard|"
    r"fidelity(?!\s+(?:bank|card|rewards|visa|credit))|"
    r"schwab(?!\s+bank)|"
    r"etrade|e[\s\-]?trade|"
    r"robinhood|coinbase|kraken"
    r")(?!\w)",
    re.IGNORECASE,
)
# Robinhood Gold Card bill pay posts through Coastal Community Bank. The
# checking memo says "CCB" / "Coastal Community Bank" and Plaid often files
# it under the brokerage merchant, including TRANSFER_OUT_INVESTMENT_*.
_CARD_BILLPAY_TEXT = re.compile(
    r"(?<!\w)(?:ccb|coastal\s+community\s+bank)(?!\w)",
    re.IGNORECASE,
)
_ACH_TEXT = re.compile(r"\bach\b", re.IGNORECASE)
_SAVINGS_TEXT = re.compile(
    r"\b(savings|hysa|high[\s\-]?yield|money[\s\-]?market|emergency[\s\-]?fund)\b",
    re.IGNORECASE,
)
_PAYMENT_TEXT = re.compile(
    r"\b(payment|autopay|auto[\s\-]?pay|thank\s+you|credit\s+card)\b",
    re.IGNORECASE,
)
# Bank interest credits are earned income. Plaid often files them as a generic
# transfer (or only as the word "interest"), which the income exclusion then drops.
_INTEREST_EARNED_TEXT = re.compile(
    r"(?<!\w)(?:"
    r"interest(?:\s+(?:earned|payment|paid|credit|income|pymt))?"
    r"|intrst(?:\s+pymnt)?"
    r")(?!\w)",
    re.IGNORECASE,
)
_INTEREST_CHARGE_TEXT = re.compile(
    r"(?<!\w)(?:interest\s+charge|purchase\s+interest|finance\s+charge)(?!\w)",
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


def memo_is_card_billpay(*parts: str | None) -> bool:
    """True for brokerage-branded credit-card bill pay (not a brokerage deposit)."""
    blob = _text_blob(*parts)
    return bool(blob and _CARD_BILLPAY_TEXT.search(blob))


def memo_has_investment_cue(*parts: str | None) -> bool:
    """True when memo text names a brokerage or a retirement account."""
    blob = _text_blob(*parts)
    return bool(blob and _INVESTMENT_TEXT.search(blob))


def _has_financial_institution_counterparty(counterparties: list[dict[str, Any]] | None) -> bool:
    if not counterparties:
        return False
    for c in counterparties:
        ctype = str(c.get("type") or "").lower()
        # payment_app (Venmo, Zelle, Cash App) is not a brokerage counterparty.
        if ctype == "financial_institution":
            return True
    return False


def _is_consumptive_category(category_key: str) -> bool:
    if not category_key:
        return False
    resolved = resolve_category_to_pfc_key(category_key) or category_key
    upper = resolved.upper().replace(".", "_").replace(" ", "_")
    return any(
        upper == primary or upper.startswith(f"{primary}_") for primary in _CONSUMPTIVE_PRIMARIES
    )


def _looks_like_investment_funding(
    *,
    merchant: str | None,
    original_description: str | None,
    description_raw: str | None,
    payment_meta: dict[str, Any] | None,
    counterparties: list[dict[str, Any]] | None,
    transaction_code: str | None,
    category_key: str,
    has_matched_investment: bool = False,
    ignore_text_heuristic: bool = False,
) -> bool:
    billpay_blob = _text_blob(
        merchant,
        original_description,
        description_raw,
        _payment_meta_blob(payment_meta),
    )
    # Plaid's investment-transfer category is wrong for Gold Card bill pay.
    # An explicit user category of that same key still wins (ignore_text_heuristic
    # is set only for manual overrides, and the category check below honors it).
    if not ignore_text_heuristic and memo_is_card_billpay(billpay_blob):
        return False
    if category_key in TRANSFER_OUT_SPENDING_SUBCATEGORIES:
        return True
    # A persisted deposit match must not reclassify rent, groceries, or other
    # purchases. Those pairs were amount coincidences; Plaid's spending
    # category is the stronger signal, including for matches already saved.
    if _is_consumptive_category(category_key):
        return False
    if has_matched_investment:
        return True
    if ignore_text_heuristic:
        return False

    blob = billpay_blob
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


def _looks_like_savings_funding(
    *,
    merchant: str | None,
    original_description: str | None,
    description_raw: str | None,
    category_key: str,
    account_subtype: str | None,
    transaction_code: str | None,
) -> bool:
    if category_key == "TRANSFER_OUT_SAVINGS" or category_key.startswith("TRANSFER_OUT_SAVINGS"):
        return True
    blob = _text_blob(merchant, original_description, description_raw)
    transferish = category_key.startswith("TRANSFER_OUT") or (transaction_code or "").lower() == "transfer"
    if transferish and _SAVINGS_TEXT.search(blob):
        return True
    if (account_subtype or "").lower() == "savings" and category_key.startswith("TRANSFER_OUT"):
        return True
    return False


# Plaid investment-transaction subtypes. A cash dividend is income; the paired
# buy that puts those dollars back into shares is a reinvestment, not new funding.
_DIVIDEND_INCOME_SUBTYPES = frozenset({
    "dividend",
    "qualified dividend",
    "non-qualified dividend",
    "nonqualified dividend",
})
_DIVIDEND_REINVEST_SUBTYPES = frozenset({
    "dividend reinvestment",
})
_DIVIDEND_REINVEST_TEXT = re.compile(r"dividend\s*reinvest", re.IGNORECASE)
_DIVIDEND_WORD_TEXT = re.compile(r"(?<!\w)dividends?(?!\w)", re.IGNORECASE)

BrokerageCashFlowKind = Literal["dividend", "reinvestment"]


def text_looks_like_cash_dividend(*parts: str | None) -> bool:
    """True for a dividend credit memo, not a dividend-reinvestment buy."""
    blob = _text_blob(*parts)
    return bool(blob and _DIVIDEND_WORD_TEXT.search(blob) and not _DIVIDEND_REINVEST_TEXT.search(blob))


def brokerage_cash_flow_kind(
    *,
    type: str | None,
    subtype: str | None,
    name: str | None,
) -> BrokerageCashFlowKind | None:
    """Cash-flow role for one investment-account activity row.

    Only dividends and dividend reinvestments belong on the cash-flow chart.
    Buys, sells, deposits, and fees stay on the Investments tab.
    """
    subtype_key = (subtype or "").strip().lower()
    type_key = (type or "").strip().lower()
    blob = name or ""
    if subtype_key in _DIVIDEND_REINVEST_SUBTYPES or _DIVIDEND_REINVEST_TEXT.search(blob):
        return "reinvestment"
    if subtype_key in _DIVIDEND_INCOME_SUBTYPES:
        return "dividend"
    # Robinhood-style memos ("Cash dividend of $7.68 from SCHD - DIVIDEND")
    # sometimes arrive with type cash and the word only in the name. A withdrawal
    # or deposit that merely mentions a dividend is a transfer, not a second credit.
    if (
        type_key == "cash"
        and subtype_key not in {"deposit", "withdrawal", "contribution", "distribution", "transfer", "send", "request"}
        and _DIVIDEND_WORD_TEXT.search(blob)
    ):
        return "dividend"
    return None


def looks_like_interest_earned(
    *,
    category_key: str,
    merchant: str | None,
    original_description: str | None,
    description_raw: str | None,
) -> bool:
    """True for interest credited to the account, not an interest charge."""
    upper = _exclusion_key(category_key)
    if upper in {"INCOME_INTEREST_EARNED", "INTEREST"}:
        return True
    if "INTEREST_CHARGE" in upper:
        return False
    blob = _text_blob(merchant, original_description, description_raw)
    if not blob or _INTEREST_CHARGE_TEXT.search(blob):
        return False
    return bool(_INTEREST_EARNED_TEXT.search(blob))


def _looks_like_card_payment(
    *,
    account_type: str | None,
    amount: float,
    merchant: str | None,
    original_description: str | None,
    description_raw: str | None,
    category_key: str,
    manual_override: bool = False,
    payment_meta: dict[str, Any] | None = None,
) -> bool:
    if category_key.startswith("LOAN_PAYMENTS"):
        return True
    # Credit-side payment posting on the card account (money moving onto the card).
    if (account_type or "").lower() == "credit" and amount < 0:
        return True
    blob = _text_blob(
        merchant,
        original_description,
        description_raw,
        _payment_meta_blob(payment_meta),
    )
    if not manual_override and memo_is_card_billpay(blob):
        return True
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
    has_matched_transfer: bool = False,
    has_matched_investment: bool = False,
    manual_override: bool = False,
) -> CashFlowRole:
    """
    Classify a transaction for Cash Flow.

    Returns:
      income / spending / investments / transfer / exclude
    """
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
            manual_override=manual_override,
            payment_meta=payment_meta,
        ):
            return "transfer"
        if not manual_override and has_matched_transfer:
            return "transfer"
        # Interest credits are income even when Plaid files them as a transfer.
        if looks_like_interest_earned(
            category_key=category_key,
            merchant=merchant,
            original_description=original_description,
            description_raw=description_raw,
        ):
            return "income"
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
        manual_override=manual_override,
        payment_meta=payment_meta,
    ):
        return "transfer"

    if _looks_like_savings_funding(
        merchant=merchant,
        original_description=original_description,
        description_raw=description_raw,
        category_key=category_key,
        account_subtype=account_subtype,
        transaction_code=transaction_code,
    ):
        return "savings"

    # A Transaction<->Transaction match is structurally certain to be a
    # transfer, never investment funding (see app.transfer_matcher's
    # module docstring) — so it must outrank _looks_like_investment_funding's
    # text heuristic below, which would otherwise still fire on a card
    # payment whose merchant/memo text also happens to look investment-ish
    # (e.g. "Robinhood" + an ACH memo), even with a confirmed match.
    if not manual_override and has_matched_transfer:
        return "transfer"

    if _looks_like_investment_funding(
        merchant=merchant,
        original_description=original_description,
        description_raw=description_raw,
        payment_meta=payment_meta,
        counterparties=counterparties,
        transaction_code=transaction_code,
        category_key=category_key,
        has_matched_investment=(has_matched_investment and not manual_override),
        ignore_text_heuristic=manual_override,
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
        has_matched_transfer=getattr(txn, "transfer_match_transaction_id", None) is not None,
        has_matched_investment=getattr(txn, "transfer_match_investment_txn_id", None) is not None,
        manual_override=bool(getattr(txn, "manual_override", False)),
    )
