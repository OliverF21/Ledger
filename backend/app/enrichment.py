"""
Helpers for Plaid transaction enrichment bundled with /transactions/sync.
No separate Enrich API product — these fields are already in the sync response.
"""

import json
from typing import Any, Optional


def extract_plaid_enrichment(txn: dict[str, Any]) -> dict[str, Any]:
    """Pull enrichment fields from a Plaid /transactions/sync transaction object."""
    pfc = txn.get("personal_finance_category") or {}
    extra: dict[str, Any] = {}
    if txn.get("counterparties"):
        extra["counterparties"] = txn["counterparties"]
    if txn.get("location"):
        extra["location"] = txn["location"]
    if pfc.get("confidence_level"):
        extra["pfc_confidence"] = pfc["confidence_level"]
    if txn.get("personal_finance_category_icon_url"):
        extra["category_icon_url"] = txn["personal_finance_category_icon_url"]
    if txn.get("name"):
        extra["description_raw"] = txn["name"]

    return {
        "merchant": txn.get("merchant_name") or txn.get("name") or "Unknown",
        "category_plaid": pfc.get("primary"),
        "category_plaid_detailed": pfc.get("detailed"),
        "merchant_logo_url": txn.get("logo_url"),
        "payment_channel": txn.get("payment_channel"),
        "enrichment_json": json.dumps(extra) if extra else None,
    }


def apply_enrichment_fields(txn: Any, txn_data: dict[str, Any]) -> None:
    """Copy parsed enrichment onto a Transaction ORM instance."""
    txn.merchant = txn_data.get("merchant", txn.merchant)
    txn.category_plaid = txn_data.get("category_plaid")
    txn.category_plaid_detailed = txn_data.get("category_plaid_detailed")
    txn.merchant_logo_url = txn_data.get("merchant_logo_url")
    txn.payment_channel = txn_data.get("payment_channel")
    txn.enrichment_json = txn_data.get("enrichment_json")


def parse_enrichment_json(raw: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
