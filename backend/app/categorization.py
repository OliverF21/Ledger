"""
Merchant-based categorization: bulk-apply a category to similar transactions,
and persistent CategoryRule matching applied automatically during sync/import.

A rule "wins" only over transactions that haven't been explicitly categorized
by the user (manual_override is not True -- some legacy rows have it as NULL
rather than False) -- a deliberate manual choice on one transaction is never
silently overwritten by a rule matching its merchant.
"""

import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Category, CategoryRule, Transaction


def find_similar_transactions(db: Session, merchant: str, exclude_id: Optional[int] = None, limit: int = 200) -> list[Transaction]:
    """
    Other non-removed transactions with the exact same merchant name
    (case-insensitive). Used to preview a bulk recategorize.

    Deliberately does NOT exclude manual_override=True rows: unlike a rule
    firing automatically on sync, applying here is an explicit, confirmed
    user action. Excluding already-manually-set rows would mean any
    merchant group that's ever been bulk-categorized once becomes
    permanently invisible to this preview - you'd have no way to bulk-fix
    your own earlier bulk choice.
    """
    q = db.query(Transaction).filter(
        Transaction.removed == False,
        func.lower(Transaction.merchant) == merchant.lower(),
    )
    if exclude_id is not None:
        q = q.filter(Transaction.id != exclude_id)
    return q.order_by(Transaction.date.desc()).limit(limit).all()


def apply_category_to_transactions(db: Session, transaction_ids: list[int], category: str) -> int:
    """Bulk-set category_user + manual_override on the given transactions. Caller commits."""
    if not transaction_ids:
        return 0
    return (
        db.query(Transaction)
        .filter(Transaction.id.in_(transaction_ids), Transaction.removed == False)
        .update({Transaction.category_user: category, Transaction.manual_override: True}, synchronize_session=False)
    )


def get_active_rules(db: Session, user_id: int = 1) -> list[tuple[CategoryRule, str]]:
    """Rules paired with their target category name, in priority order (first match wins).
    NULL priority (never reordered) falls back to creation order."""
    rows = (
        db.query(CategoryRule, Category.name)
        .join(Category, CategoryRule.category_id == Category.id)
        .filter(CategoryRule.user_id == user_id)
        .order_by(func.coalesce(CategoryRule.priority, CategoryRule.id).asc())
        .all()
    )
    return [(rule, name) for rule, name in rows]


def pattern_matches(merchant: str, merchant_pattern: str) -> bool:
    """Case-insensitive regex match with substring fallback for invalid regexes."""
    try:
        return bool(re.search(merchant_pattern, merchant, re.IGNORECASE))
    except re.error:
        return merchant_pattern.lower() in merchant.lower()


def match_rule(merchant: str, rules: list[tuple[CategoryRule, str]]) -> Optional[str]:
    """Return the category name of the first rule whose pattern matches merchant, else None."""
    for rule, category_name in rules:
        if pattern_matches(merchant, rule.merchant_pattern):
            return category_name
    return None


def apply_rules_to_transaction(txn: Transaction, rules: list[tuple[CategoryRule, str]]) -> None:
    """Auto-categorize a transaction in place if a rule matches and it hasn't been manually set."""
    if txn.manual_override:
        return
    category_name = match_rule(txn.merchant or "", rules)
    if category_name:
        txn.category_user = category_name


def apply_rule_to_existing_transactions(db: Session, merchant_pattern: str, category_name: str) -> int:
    """
    Backfill a freshly-created rule onto existing non-manually-categorized
    transactions so the effect is visible immediately, not just on next sync.
    """
    candidates = (
        db.query(Transaction)
        .filter(Transaction.removed == False, Transaction.manual_override.isnot(True))
        .all()
    )
    matched_ids = []
    for txn in candidates:
        if pattern_matches(txn.merchant or "", merchant_pattern):
            matched_ids.append(txn.id)

    if not matched_ids:
        return 0
    return (
        db.query(Transaction)
        .filter(Transaction.id.in_(matched_ids))
        .update({Transaction.category_user: category_name}, synchronize_session=False)
    )


def revert_deleted_rule_from_existing_transactions(
    db: Session,
    merchant_pattern: str,
    remaining_rules: list[tuple[CategoryRule, str]],
) -> int:
    """
    Recalculate auto-categorized transactions that matched a deleted rule.

    Manual overrides are preserved. Non-manual transactions that no longer
    match any remaining rule fall back to Plaid by clearing category_user.
    """
    candidates = (
        db.query(Transaction)
        .filter(Transaction.removed == False, Transaction.manual_override.isnot(True))
        .all()
    )

    updated = 0
    for txn in candidates:
        merchant = txn.merchant or ""
        if not pattern_matches(merchant, merchant_pattern):
            continue

        next_category = match_rule(merchant, remaining_rules)
        next_value = next_category or None
        if txn.category_user != next_value:
            txn.category_user = next_value
            updated += 1

    return updated
