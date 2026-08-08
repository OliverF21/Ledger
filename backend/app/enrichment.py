"""
Helpers for Plaid transaction enrichment bundled with /transactions/sync.
No separate Enrich API product — these fields are already in the sync response.
"""

from __future__ import annotations

import json
from typing import Any, Optional


def _normalize_counterparties(raw: Any) -> list[dict[str, Any]] | None:
    """Keep a stable, trimmed shape for counterparty objects from Plaid."""
    if not isinstance(raw, list) or not raw:
        return None
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry = {
            key: item.get(key)
            for key in (
                "name",
                "type",
                "website",
                "entity_id",
                "logo_url",
                "confidence_level",
                "phone_number",
            )
            if item.get(key) is not None
        }
        if entry:
            normalized.append(entry)
    return normalized or None


def _normalize_payment_meta(raw: Any) -> dict[str, Any] | None:
    """Keep non-null payment_meta fields (ACH / inter-bank transfer hints)."""
    if not isinstance(raw, dict):
        return None
    cleaned = {
        key: value
        for key, value in raw.items()
        if value is not None and value != ""
    }
    return cleaned or None


def extract_plaid_enrichment(txn: dict[str, Any]) -> dict[str, Any]:
    """Pull enrichment fields from a Plaid /transactions/sync transaction object."""
    pfc = txn.get("personal_finance_category") or {}
    extra: dict[str, Any] = {}

    counterparties = _normalize_counterparties(txn.get("counterparties"))
    if counterparties:
        extra["counterparties"] = counterparties

    location = txn.get("location")
    if isinstance(location, dict) and any(v is not None and v != "" for v in location.values()):
        extra["location"] = location

    if pfc.get("confidence_level"):
        extra["pfc_confidence"] = pfc["confidence_level"]
    if txn.get("personal_finance_category_icon_url"):
        extra["category_icon_url"] = txn["personal_finance_category_icon_url"]
    if txn.get("name"):
        extra["description_raw"] = txn["name"]

    payment_meta = _normalize_payment_meta(txn.get("payment_meta"))
    if payment_meta:
        extra["payment_meta"] = payment_meta

    original_description = txn.get("original_description")
    transaction_code = txn.get("transaction_code")

    return {
        "merchant": txn.get("merchant_name") or txn.get("name") or "Unknown",
        "category_plaid": pfc.get("primary"),
        "category_plaid_detailed": pfc.get("detailed"),
        "merchant_logo_url": txn.get("logo_url"),
        "payment_channel": txn.get("payment_channel"),
        "original_description": original_description,
        "transaction_code": transaction_code,
        "enrichment_json": json.dumps(extra) if extra else None,
    }


def apply_enrichment_fields(txn: Any, txn_data: dict[str, Any]) -> None:
    """Copy parsed enrichment onto a Transaction ORM instance."""
    txn.merchant = txn_data.get("merchant", txn.merchant)
    txn.category_plaid = txn_data.get("category_plaid")
    txn.category_plaid_detailed = txn_data.get("category_plaid_detailed")
    txn.merchant_logo_url = txn_data.get("merchant_logo_url")
    txn.payment_channel = txn_data.get("payment_channel")
    if "original_description" in txn_data:
        txn.original_description = txn_data.get("original_description")
    if "transaction_code" in txn_data:
        txn.transaction_code = txn_data.get("transaction_code")
    txn.enrichment_json = txn_data.get("enrichment_json")


def parse_enrichment_json(raw: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
