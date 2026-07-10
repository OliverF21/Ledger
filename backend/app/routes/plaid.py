"""
Plaid Link integration endpoints.
- POST /plaid/create_link_token: Create link token for frontend (new link or update mode)
- POST /plaid/set_access_token: Exchange public token for access token
- GET /accounts: List linked accounts
"""

import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.errors import log_and_raise
from app.models import Item, Account, BalanceSnapshot, Transaction
from app.plaid_service import PlaidService
from app.plaid_errors import extract_plaid_error, is_login_required
from app.security import encrypt_token, decrypt_token
from app.sync_engine import get_real_items, sync_item

router = APIRouter(prefix="/plaid", tags=["plaid"])


class LinkTokenRequest(BaseModel):
    """Pass item_id (internal DB id) to open Plaid Link in update mode."""
    item_id: Optional[int] = None
    redirect_uri: Optional[str] = None


class LinkTokenResponse(BaseModel):
    link_token: str
    update_mode: bool = False
    oauth_redirect_configured: bool = False


class SetAccessTokenRequest(BaseModel):
    public_token: str


class SetAccessTokenResponse(BaseModel):
    success: bool
    item_id: str
    updated: bool = False


class AccountInfo(BaseModel):
    id: int
    item_id: int
    institution_name: Optional[str]
    institution_logo: Optional[str] = None
    institution_color: Optional[str] = None
    plaid_account_id: str
    name: str
    type: str
    subtype: str
    current_balance: float


class AccountsResponse(BaseModel):
    accounts: list[AccountInfo]


class ItemSyncInfo(BaseModel):
    id: int
    institution_name: Optional[str]
    sync_status: Optional[str]
    last_sync_error: Optional[str]
    last_synced_at: Optional[str]


class SyncStatusResponse(BaseModel):
    last_synced_at: Optional[str]
    item_count: int
    environment: str
    items: list[ItemSyncInfo]


class SyncItemResult(BaseModel):
    item_id: int
    institution_name: Optional[str]
    status: str  # ok | login_required | error
    synced: int = 0
    removed: int = 0
    enrichment_backfilled: int = 0
    error: Optional[str] = None


class SyncResponse(BaseModel):
    success: bool
    message: str
    transactions_synced: int = 0
    enrichment_backfilled: int = 0
    failed_count: int = 0
    items: list[SyncItemResult] = []


class DeleteItemResponse(BaseModel):
    success: bool
    accounts_removed: int
    transactions_removed: int


def _is_stale_institution_name(name: Optional[str]) -> bool:
    """True when DB holds a raw Plaid institution_id instead of a display name."""
    return PlaidService.is_plaid_institution_id(name)


def _refresh_institution_metadata(db: Session, items: list[Item]) -> None:
    """Backfill institution names, logos, and brand colors."""
    updated = False
    for item in items:
        if PlaidService.refresh_item_institution_metadata(item):
            updated = True
    if updated:
        db.commit()


def _item_sync_info(item: Item) -> ItemSyncInfo:
    return ItemSyncInfo(
        id=item.id,
        institution_name=item.institution_name,
        sync_status=item.sync_status or "ok",
        last_sync_error=item.last_sync_error,
        last_synced_at=item.last_synced_at.isoformat() if item.last_synced_at else None,
    )


def _upsert_accounts(db: Session, item: Item, accounts_data: list[dict]) -> None:
    """Create or refresh Account rows for a Plaid Item."""
    today = date.today()
    existing_by_plaid = {acc.plaid_account_id: acc for acc in item.accounts}

    for acc_data in accounts_data:
        account = existing_by_plaid.get(acc_data["plaid_account_id"])
        if account:
            account.name = acc_data["name"]
            account.type = acc_data["type"]
            account.subtype = acc_data["subtype"]
            account.current_balance = acc_data["current_balance"]
            continue

        account = Account(
            item_id=item.id,
            plaid_account_id=acc_data["plaid_account_id"],
            name=acc_data["name"],
            type=acc_data["type"],
            subtype=acc_data["subtype"],
            current_balance=acc_data["current_balance"],
        )
        db.add(account)
        db.flush()
        db.add(BalanceSnapshot(
            account_id=account.id,
            balance=acc_data["current_balance"],
            snapshot_date=today,
        ))


@router.post("/create_link_token", response_model=LinkTokenResponse)
async def create_link_token(body: LinkTokenRequest, db: Session = Depends(get_db)):
    """
    Create a Plaid Link token for the frontend.
    Pass item_id to open Link in update mode (re-auth / additional consent).
    """
    if not PlaidService.is_configured():
        raise HTTPException(status_code=409, detail="Plaid is not configured. Add your keys in Settings → Plaid.")
    try:
        access_token = None
        update_mode = False
        if body.item_id is not None:
            item = db.query(Item).filter(Item.id == body.item_id, Item.user_id == 1).first()
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            if item.item_id in ("manual_import", "test_item"):
                raise HTTPException(status_code=400, detail="Cannot update a non-Plaid item")
            access_token = decrypt_token(item.access_token_encrypted)
            update_mode = True

        link_token, oauth_redirect_configured = PlaidService.create_link_token(
            user_id=1,
            access_token=access_token,
            redirect_uri=body.redirect_uri,
        )
        return LinkTokenResponse(
            link_token=link_token,
            update_mode=update_mode,
            oauth_redirect_configured=oauth_redirect_configured,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log_and_raise(e, status_code=500)


@router.post("/set_access_token", response_model=SetAccessTokenResponse)
async def set_access_token(
    request: SetAccessTokenRequest,
    db: Session = Depends(get_db),
):
    """
    Exchange public_token (from Plaid Link) for access_token.
    Creates a new Item or updates an existing one when Link ran in update mode.
    """
    try:
        access_token, plaid_item_id = PlaidService.exchange_public_token(request.public_token)
        encrypted_token = encrypt_token(access_token)
        accounts_data, institution_details = PlaidService.get_accounts_with_institution(access_token)

        existing = db.query(Item).filter(
            Item.user_id == 1,
            Item.item_id == plaid_item_id,
        ).first()

        if existing:
            existing.access_token_encrypted = encrypted_token
            PlaidService.apply_institution_metadata(existing, institution_details)
            existing.sync_status = "ok"
            existing.last_sync_error = None
            _upsert_accounts(db, existing, accounts_data)
            db.commit()
            return SetAccessTokenResponse(
                success=True,
                item_id=plaid_item_id,
                updated=True,
            )

        item = Item(
            user_id=1,
            item_id=plaid_item_id,
            institution_name=institution_details.get('name'),
            institution_id=institution_details.get('institution_id'),
            institution_logo=institution_details.get('logo'),
            institution_color=institution_details.get('primary_color'),
            access_token_encrypted=encrypted_token,
            sync_status="ok",
        )
        db.add(item)
        db.flush()
        _upsert_accounts(db, item, accounts_data)
        db.commit()

        return SetAccessTokenResponse(success=True, item_id=plaid_item_id, updated=False)
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


@router.get("/accounts", response_model=AccountsResponse)
async def get_accounts(db: Session = Depends(get_db)):
    """List all linked accounts from REAL Plaid connections (not CSV imports)."""
    try:
        accounts = db.query(Account).join(Item).filter(
            Item.user_id == 1,
            Item.item_id != "manual_import",
        ).all()
        items = {acc.item for acc in accounts}
        _refresh_institution_metadata(db, list(items))
        accounts_response = [
            AccountInfo(
                id=acc.id,
                item_id=acc.item_id,
                institution_name=acc.item.institution_name,
                institution_logo=acc.item.institution_logo,
                institution_color=acc.item.institution_color,
                plaid_account_id=acc.plaid_account_id,
                name=acc.name,
                type=acc.type,
                subtype=acc.subtype,
                current_balance=float(acc.current_balance or 0),
            )
            for acc in accounts
        ]
        return AccountsResponse(accounts=accounts_response)
    except Exception as e:
        log_and_raise(e, status_code=400)


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(db: Session = Depends(get_db)):
    """Return the last sync timestamp, per-Item health, and environment info."""
    try:
        items = get_real_items(db)
        last_synced = max(
            (item.last_synced_at for item in items if item.last_synced_at),
            default=None,
        )
        return SyncStatusResponse(
            last_synced_at=last_synced.isoformat() if last_synced else None,
            item_count=len(items),
            environment=os.getenv("PLAID_ENV", "sandbox"),
            items=[_item_sync_info(item) for item in items],
        )
    except Exception as e:
        log_and_raise(e)


@router.post("/sync", response_model=SyncResponse)
async def sync_transactions(db: Session = Depends(get_db)):
    """
    Trigger a sync of transactions for all linked items.
    Also refreshes account balances from Plaid and takes a balance snapshot for today.
    """
    if not PlaidService.is_configured():
        raise HTTPException(status_code=409, detail="Plaid is not configured. Add your keys in Settings → Plaid.")
    try:
        real_items = get_real_items(db)
        total_synced = 0
        total_removed = 0
        total_backfilled = 0
        item_results: list[SyncItemResult] = []

        for item in real_items:
            try:
                stats = sync_item(db, item)
                total_synced += stats["synced"]
                total_removed += stats["removed"]
                total_backfilled += stats.get("enrichment_backfilled", 0)
                item_results.append(SyncItemResult(
                    item_id=item.id,
                    institution_name=item.institution_name,
                    status="ok",
                    synced=stats["synced"],
                    removed=stats["removed"],
                    enrichment_backfilled=stats.get("enrichment_backfilled", 0),
                ))
            except Exception as exc:
                db.rollback()
                db.refresh(item)
                code, msg = extract_plaid_error(exc)
                status = "login_required" if is_login_required(code) else "error"
                item_results.append(SyncItemResult(
                    item_id=item.id,
                    institution_name=item.institution_name,
                    status=status,
                    error=(msg or str(exc))[:500],
                ))

        failed_count = sum(1 for r in item_results if r.status != "ok")
        parts = [f"Synced {total_synced} new transactions"]
        if total_removed:
            parts.append(f"marked {total_removed} as removed")
        if total_backfilled:
            parts.append(f"backfilled enrichment on {total_backfilled} existing transactions")
        if failed_count:
            parts.append(f"{failed_count} institution{'s' if failed_count != 1 else ''} failed")
        message = ", ".join(parts)

        return SyncResponse(
            success=failed_count == 0,
            message=message,
            transactions_synced=total_synced,
            enrichment_backfilled=total_backfilled,
            failed_count=failed_count,
            items=item_results,
        )
    except Exception as e:
        log_and_raise(e, status_code=400)


@router.delete("/item/{item_id}", response_model=DeleteItemResponse)
async def delete_item(item_id: int, db: Session = Depends(get_db)):
    """
    Remove a linked Plaid item and scrub all associated data:
    accounts, transactions, balance snapshots (all cascade from Item).
    """
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == 1).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    accounts_count = len(item.accounts)
    transactions_count = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Account.item_id == item_id)
        .count()
    )

    db.delete(item)
    db.commit()

    return DeleteItemResponse(
        success=True,
        accounts_removed=accounts_count,
        transactions_removed=transactions_count,
    )
