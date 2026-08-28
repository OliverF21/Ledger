"""Sync read-only crypto wallets into Account + BalanceSnapshot for net worth."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.alchemy_service import (
    AlchemyConfigError,
    alchemy_api_key,
    fetch_allowlisted_balances,
    normalize_address,
    require_alchemy_api_key,
)
from app.crypto_tokens import CHAIN_KEY, CRYPTO_ITEM_ID
from app.models import Account, BalanceSnapshot, CryptoHolding, CryptoWallet, Item

logger = logging.getLogger("ledger")


def get_or_create_crypto_item(db: Session, user_id: int = 1) -> Item:
    item = (
        db.query(Item)
        .filter(Item.user_id == user_id, Item.item_id == CRYPTO_ITEM_ID)
        .first()
    )
    if item:
        return item
    item = Item(
        user_id=user_id,
        item_id=CRYPTO_ITEM_ID,
        institution_name="Crypto Wallets",
        access_token_encrypted="",
    )
    db.add(item)
    db.flush()
    return item


def _upsert_today_snapshot(db: Session, account: Account, balance: Decimal) -> None:
    today = date.today()
    existing = (
        db.query(BalanceSnapshot)
        .filter(
            BalanceSnapshot.account_id == account.id,
            BalanceSnapshot.snapshot_date == today,
        )
        .first()
    )
    if existing:
        existing.balance = balance
    else:
        db.add(
            BalanceSnapshot(
                account_id=account.id,
                balance=balance,
                snapshot_date=today,
            )
        )


def sync_wallet(db: Session, wallet: CryptoWallet, *, api_key: str | None = None) -> dict:
    """Refresh one wallet's holdings and linked Account balance. Commits."""
    key = api_key if api_key is not None else require_alchemy_api_key()
    try:
        rows = fetch_allowlisted_balances(key, wallet.address)
        total_usd = sum((r["usd_value"] for r in rows), Decimal("0"))

        # Replace holdings
        db.query(CryptoHolding).filter(CryptoHolding.wallet_id == wallet.id).delete()
        for r in rows:
            if r["balance"] == 0 and r["usd_value"] == 0:
                continue  # skip empty dust/zeros from UI clutter
            db.add(
                CryptoHolding(
                    wallet_id=wallet.id,
                    symbol=r["symbol"],
                    contract_address=r["contract_address"],
                    decimals=r["decimals"],
                    balance=r["balance"],
                    usd_value=r["usd_value"],
                )
            )

        account = db.query(Account).filter(Account.id == wallet.account_id).first()
        if not account:
            raise RuntimeError(f"Crypto wallet {wallet.id} has no linked account")
        account.current_balance = total_usd
        account.updated_at = datetime.utcnow()
        if wallet.label:
            account.name = wallet.label
        _upsert_today_snapshot(db, account, total_usd)

        wallet.last_synced_at = datetime.utcnow()
        wallet.last_error = None
        wallet.updated_at = datetime.utcnow()
        db.commit()
        return {
            "wallet_id": wallet.id,
            "usd_total": float(total_usd),
            "holding_count": len([r for r in rows if r["balance"] != 0]),
            "status": "ok",
        }
    except Exception as exc:
        db.rollback()
        row = db.query(CryptoWallet).filter(CryptoWallet.id == wallet.id).first()
        if row:
            row.last_error = str(exc)[:500]
            row.updated_at = datetime.utcnow()
            db.commit()
        raise


def sync_crypto_wallets(db: Session, user_id: int = 1) -> dict:
    """Sync all wallets for the user. No-op (returns skipped) if Alchemy key missing."""
    key = alchemy_api_key()
    if not key:
        return {"synced": 0, "failed": 0, "skipped": True, "reason": "Alchemy API key not set"}

    wallets = (
        db.query(CryptoWallet)
        .filter(CryptoWallet.user_id == user_id)
        .all()
    )
    synced = 0
    failed = 0
    for wallet in wallets:
        try:
            sync_wallet(db, wallet, api_key=key)
            synced += 1
        except Exception:
            failed += 1
            logger.exception("crypto sync failed for wallet %s", wallet.id)
    return {"synced": synced, "failed": failed, "skipped": False}


def create_wallet(
    db: Session,
    *,
    address: str,
    label: str | None = None,
    user_id: int = 1,
) -> CryptoWallet:
    """Create wallet + Account under synthetic Item, then sync once."""
    addr = normalize_address(address)
    existing = (
        db.query(CryptoWallet)
        .filter(CryptoWallet.user_id == user_id, CryptoWallet.address == addr)
        .first()
    )
    if existing:
        raise ValueError("That wallet address is already added.")

    item = get_or_create_crypto_item(db, user_id)
    name = (label or "").strip() or addr
    account = Account(
        item_id=item.id,
        plaid_account_id=f"crypto:{addr}",
        name=name,
        type="crypto",
        subtype="wallet",
        current_balance=Decimal("0"),
    )
    db.add(account)
    db.flush()

    wallet = CryptoWallet(
        user_id=user_id,
        address=addr,
        label=(label or "").strip() or None,
        chain=CHAIN_KEY,
        account_id=account.id,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)

    try:
        sync_wallet(db, wallet)
    except AlchemyConfigError:
        wallet.last_error = "Alchemy API key not set — add it in Settings → Crypto wallets"
        db.commit()
    except Exception as exc:
        # Wallet is still saved; last_error set by sync_wallet
        logger.exception("initial crypto sync failed for %s", addr)
        if not wallet.last_error:
            wallet.last_error = str(exc)[:500]
            db.commit()

    db.refresh(wallet)
    return wallet


def wipe_wallet(db: Session, wallet_id: int, user_id: int = 1) -> None:
    """Hard-delete wallet, holdings, and linked Account (cascades snapshots)."""
    wallet = (
        db.query(CryptoWallet)
        .filter(CryptoWallet.id == wallet_id, CryptoWallet.user_id == user_id)
        .first()
    )
    if not wallet:
        raise LookupError("Wallet not found")

    account_id = wallet.account_id
    db.query(CryptoHolding).filter(CryptoHolding.wallet_id == wallet.id).delete()
    db.delete(wallet)
    db.flush()

    account = db.query(Account).filter(Account.id == account_id).first()
    if account:
        db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == account.id).delete()
        db.delete(account)
    db.commit()
