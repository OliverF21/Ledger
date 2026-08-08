"""
Incremental transaction sync logic using Plaid's cursor-based /transactions/sync
endpoint. Shared by the manual "Sync now" route (routes/plaid.py) and the
background scheduler (scheduler.py) so both paths apply removed-transaction
handling and balance snapshots identically.
"""

import logging
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.categorization import apply_rules_to_transaction, get_active_rules
from app.enrichment import apply_enrichment_fields
from app.models import Account, BalanceSnapshot, Holding, InvestmentTransaction, Item, Security, Transaction
from app.plaid_service import PlaidService
from app.plaid_errors import extract_plaid_error, is_login_required
from app.security import decrypt_token

logger = logging.getLogger("ledger")

_MAX_SYNC_ERROR_LEN = 500


def _record_item_sync_failure(db: Session, item_id: int, exc: BaseException) -> None:
    """Persist sync_status on the Item after a failed sync attempt."""
    code, msg = extract_plaid_error(exc)
    row = db.query(Item).filter(Item.id == item_id).first()
    if not row:
        return
    row.sync_status = "login_required" if is_login_required(code) else "error"
    row.last_sync_error = (msg or str(exc))[:_MAX_SYNC_ERROR_LEN]
    db.commit()


def sync_item(db: Session, item: Item) -> dict:
    """
    Sync one Plaid Item: pull new/modified/removed transactions since the
    last cursor, refresh account balances, and take today's balance
    snapshot if one doesn't already exist.

    Commits on success. Caller is responsible for rollback on exception.
    Returns {"synced": int, "removed": int, "enrichment_backfilled": int}.
    """
    try:
        return _sync_item_inner(db, item)
    except Exception as exc:
        db.rollback()
        _record_item_sync_failure(db, item.id, exc)
        raise


def _sync_item_inner(db: Session, item: Item) -> dict:
    """
    Inner sync implementation. On success clears sync_status; failures are
    recorded by sync_item()'s outer handler.
    """
    access_token = decrypt_token(item.access_token_encrypted)

    PlaidService.refresh_item_institution_metadata(item)

    # Build Plaid account_id → internal Account.id mapping
    plaid_to_internal = {acc.plaid_account_id: acc.id for acc in item.accounts}
    rules = get_active_rules(db)

    # Plaid's /transactions/sync is paginated — loop until has_more is false,
    # persisting the cursor after each page. Per-page commits mean a mid-loop
    # crash leaves the DB resumable from the last successful cursor instead of
    # losing all progress or re-processing already-handled pages.
    total_synced = 0
    total_removed = 0
    cursor = item.last_sync_cursor
    has_more = True

    while has_more:
        sync_result = PlaidService.sync_transactions(access_token, cursor)

        removed_ids = sync_result.get("removed", [])
        if removed_ids:
            db.query(Transaction).filter(
                Transaction.plaid_transaction_id.in_(removed_ids)
            ).update({Transaction.removed: True})

        page_synced = 0
        for txn_data in sync_result.get("transactions", []):
            existing = db.query(Transaction).filter(
                Transaction.plaid_transaction_id == txn_data["plaid_transaction_id"]
            ).first()

            if not existing:
                txn = Transaction(
                    account_id=plaid_to_internal.get(txn_data.get("account_id")),
                    plaid_transaction_id=txn_data["plaid_transaction_id"],
                    merchant=txn_data.get("merchant"),
                    amount=txn_data.get("amount"),
                    date=txn_data.get("date"),
                    category_plaid=txn_data.get("category_plaid"),
                    category_plaid_detailed=txn_data.get("category_plaid_detailed"),
                    merchant_logo_url=txn_data.get("merchant_logo_url"),
                    payment_channel=txn_data.get("payment_channel"),
                    original_description=txn_data.get("original_description"),
                    transaction_code=txn_data.get("transaction_code"),
                    enrichment_json=txn_data.get("enrichment_json"),
                    pending=txn_data.get("pending", False),
                )
                apply_rules_to_transaction(txn, rules)
                db.add(txn)
                page_synced += 1
            else:
                existing.pending = txn_data.get("pending", False)
                existing.amount = txn_data.get("amount")
                apply_enrichment_fields(existing, txn_data)
                apply_rules_to_transaction(existing, rules)

        cursor = sync_result.get("next_cursor")
        has_more = sync_result.get("has_more", False)
        item.last_sync_cursor = cursor
        item.last_synced_at = datetime.utcnow()
        db.commit()

        total_synced += page_synced
        total_removed += len(removed_ids)

    # Balances aren't paginated — refresh once, after all transaction pages are done
    refresh_item_balances(db, item, access_token)
    db.commit()

    enrichment_backfilled = backfill_enrichment(db, item, access_token, rules)

    try:
        sync_investments(db, item)
    except Exception:
        db.rollback()
        logger.exception("sync_investments failed for item %s; bank sync unaffected", item.item_id)

    item.sync_status = "ok"
    item.last_sync_error = None
    db.commit()

    return {
        "synced": total_synced,
        "removed": total_removed,
        "enrichment_backfilled": enrichment_backfilled,
    }


def refresh_item_balances(db: Session, item: Item, access_token: str) -> None:
    """Refresh account balances from Plaid and take today's snapshot if missing."""
    fresh_accounts = PlaidService.get_accounts(access_token)
    today = date.today()
    for acc_data in fresh_accounts:
        account = db.query(Account).filter(
            Account.item_id == item.id,
            Account.plaid_account_id == acc_data["plaid_account_id"],
        ).first()
        if account:
            account.current_balance = acc_data["current_balance"]
            existing_snap = db.query(BalanceSnapshot).filter(
                BalanceSnapshot.account_id == account.id,
                BalanceSnapshot.snapshot_date == today,
            ).first()
            if not existing_snap:
                db.add(BalanceSnapshot(
                    account_id=account.id,
                    balance=acc_data["current_balance"],
                    snapshot_date=today,
                ))


def sync_investments(db: Session, item: Item) -> dict:
    """
    Pull holdings (and recent investment activity) for one Plaid Item and
    upsert into Security/Holding/InvestmentTransaction. Bank-only Items
    (no investment accounts) are skipped silently.

    Commits on success. Caller is responsible for rollback on exception.
    Returns {"holdings_upserted": int, "holdings_removed": int}.
    """
    access_token = decrypt_token(item.access_token_encrypted)

    try:
        holdings_data = PlaidService.get_investment_holdings(access_token)
    except ValueError as e:
        message = str(e)
        if "NO_INVESTMENT_ACCOUNTS" in message:
            return {"holdings_upserted": 0, "holdings_removed": 0}
        if "PRODUCT_NOT_READY" in message:
            logger.info("Investments product not ready yet for item %s; will retry next sync", item.item_id)
            return {"holdings_upserted": 0, "holdings_removed": 0}
        raise

    investment_account_ids = {
        acc.plaid_account_id: acc.id for acc in item.accounts if acc.type == "investment"
    }
    if not investment_account_ids:
        return {"holdings_upserted": 0, "holdings_removed": 0}

    # Upsert securities by plaid_security_id
    security_id_map: dict[str, int] = {}
    for sec in holdings_data.get("securities", []):
        plaid_security_id = sec["security_id"]
        existing = db.query(Security).filter(Security.plaid_security_id == plaid_security_id).first()
        close_price_as_of = sec.get("close_price_as_of")
        close_price_as_of = date.fromisoformat(close_price_as_of) if close_price_as_of else None
        if not existing:
            existing = Security(plaid_security_id=plaid_security_id)
            db.add(existing)
        existing.ticker_symbol = sec.get("ticker_symbol")
        existing.name = sec.get("name")
        existing.type = sec.get("type")
        existing.subtype = sec.get("subtype")
        existing.close_price = sec.get("close_price")
        existing.close_price_as_of = close_price_as_of
        existing.iso_currency_code = sec.get("iso_currency_code")
        existing.is_cash_equivalent = sec.get("is_cash_equivalent", False)
        existing.updated_at = datetime.utcnow()
        db.flush()
        security_id_map[plaid_security_id] = existing.id

    # Upsert holdings by (account_id, security_id); track which survive for pruning
    seen_holding_keys: set[tuple[int, int]] = set()
    holdings_upserted = 0
    for h in holdings_data.get("holdings", []):
        account_id = investment_account_ids.get(h.get("account_id"))
        security_id = security_id_map.get(h.get("security_id"))
        if account_id is None or security_id is None:
            continue

        existing = db.query(Holding).filter(
            Holding.account_id == account_id,
            Holding.security_id == security_id,
        ).first()
        if not existing:
            existing = Holding(account_id=account_id, security_id=security_id)
            db.add(existing)
        existing.quantity = h.get("quantity")
        existing.institution_price = h.get("institution_price")
        existing.institution_value = h.get("institution_value")
        existing.cost_basis = h.get("cost_basis")
        existing.iso_currency_code = h.get("iso_currency_code")
        existing.unofficial_currency_code = h.get("unofficial_currency_code")
        existing.updated_at = datetime.utcnow()
        seen_holding_keys.add((account_id, security_id))
        holdings_upserted += 1

    # Prune closed positions: holdings on this item's investment accounts no longer returned
    holdings_removed = 0
    existing_holdings = (
        db.query(Holding)
        .filter(Holding.account_id.in_(investment_account_ids.values()))
        .all()
    )
    for holding in existing_holdings:
        if (holding.account_id, holding.security_id) not in seen_holding_keys:
            db.delete(holding)
            holdings_removed += 1

    db.commit()

    sync_investment_transactions(db, item, access_token, investment_account_ids, security_id_map)

    return {"holdings_upserted": holdings_upserted, "holdings_removed": holdings_removed}


def sync_investment_transactions(
    db: Session,
    item: Item,
    access_token: str,
    investment_account_ids: dict[str, int],
    security_id_map: dict[str, int],
) -> int:
    """Fetch the last 24 months of investment activity (paginated) and upsert rows."""
    today = date.today()
    year, month = today.year, today.month - 24
    while month <= 0:
        month += 12
        year -= 1
    start_date = date(year, month, 1)

    upserted = 0
    offset = 0
    count = 500
    while True:
        try:
            page = PlaidService.get_investment_transactions(
                access_token, start_date, today, offset=offset, count=count
            )
        except ValueError:
            logger.exception("Failed to fetch investment transactions for item %s", item.item_id)
            break

        # Securities referenced only in transactions (not currently held) still need mapping
        for sec in page.get("securities", []):
            plaid_security_id = sec["security_id"]
            if plaid_security_id in security_id_map:
                continue
            existing = db.query(Security).filter(Security.plaid_security_id == plaid_security_id).first()
            if not existing:
                close_price_as_of = sec.get("close_price_as_of")
                existing = Security(
                    plaid_security_id=plaid_security_id,
                    ticker_symbol=sec.get("ticker_symbol"),
                    name=sec.get("name"),
                    type=sec.get("type"),
                    subtype=sec.get("subtype"),
                    close_price=sec.get("close_price"),
                    close_price_as_of=date.fromisoformat(close_price_as_of) if close_price_as_of else None,
                    iso_currency_code=sec.get("iso_currency_code"),
                    is_cash_equivalent=sec.get("is_cash_equivalent", False),
                )
                db.add(existing)
                db.flush()
            security_id_map[plaid_security_id] = existing.id

        batch = page.get("investment_transactions", [])
        for txn in batch:
            account_id = investment_account_ids.get(txn.get("account_id"))
            if account_id is None:
                continue
            plaid_id = txn["investment_transaction_id"]
            existing = db.query(InvestmentTransaction).filter(
                InvestmentTransaction.plaid_investment_transaction_id == plaid_id
            ).first()
            if not existing:
                existing = InvestmentTransaction(
                    account_id=account_id,
                    plaid_investment_transaction_id=plaid_id,
                )
                db.add(existing)
            existing.security_id = security_id_map.get(txn.get("security_id"))
            existing.name = txn.get("name", "")
            existing.type = txn.get("type", "")
            existing.subtype = txn.get("subtype")
            existing.amount = txn.get("amount")
            existing.quantity = txn.get("quantity")
            existing.price = txn.get("price")
            existing.fees = txn.get("fees")
            raw_date = txn.get("date")
            existing.date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
            upserted += 1

        total = page.get("total_investment_transactions", 0)
        offset += len(batch)
        db.commit()
        if not batch or offset >= total:
            break

    return upserted


def backfill_enrichment(
    db: Session,
    item: Item,
    access_token: str,
    rules: list | None = None,
) -> int:
    """
    Re-fetch enrichment for existing Plaid transactions via /transactions/get.

    Incremental /transactions/sync only returns new/modified rows, so rows
  synced before enrichment support was added never get updated otherwise.
    """
    if rules is None:
        rules = get_active_rules(db)

    account_ids = [acc.id for acc in item.accounts]
    if not account_ids:
        return 0

    bounds = (
        db.query(func.min(Transaction.date), func.max(Transaction.date))
        .filter(
            Transaction.account_id.in_(account_ids),
            Transaction.plaid_transaction_id.isnot(None),
            Transaction.removed == False,
        )
        .one()
    )
    start_date, end_date = bounds
    if not start_date or not end_date:
        return 0

    unenriched_ids = {
        plaid_id
        for (plaid_id,) in db.query(Transaction.plaid_transaction_id)
        .filter(
            Transaction.account_id.in_(account_ids),
            Transaction.plaid_transaction_id.isnot(None),
            Transaction.removed == False,
            (
                (Transaction.category_plaid_detailed.is_(None))
                | (Transaction.original_description.is_(None))
                | (Transaction.transaction_code.is_(None))
            ),
        )
        .all()
    }
    if not unenriched_ids:
        return 0

    updated = 0
    for raw_txn in PlaidService.iter_transactions(access_token, start_date, end_date):
        plaid_id = raw_txn.get("transaction_id")
        if plaid_id not in unenriched_ids:
            continue
        existing = db.query(Transaction).filter(
            Transaction.plaid_transaction_id == plaid_id
        ).first()
        if not existing:
            continue
        txn_data = PlaidService.parse_sync_transaction(raw_txn)
        apply_enrichment_fields(existing, txn_data)
        apply_rules_to_transaction(existing, rules)
        unenriched_ids.discard(plaid_id)
        updated += 1
        if not unenriched_ids:
            break

    if updated:
        item.last_synced_at = datetime.utcnow()
        db.commit()

    return updated


def get_real_items(db: Session, user_id: int = 1) -> list[Item]:
    """Items backed by a real Plaid connection (excludes manual/test/crypto items)."""
    from app.crypto_tokens import PLAID_SYNC_EXCLUDED_ITEMS

    return (
        db.query(Item)
        .filter(Item.user_id == user_id, Item.item_id.notin_(list(PLAID_SYNC_EXCLUDED_ITEMS)))
        .all()
    )
