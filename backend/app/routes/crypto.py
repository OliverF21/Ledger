"""Read-only crypto wallet endpoints for Robinhood Chain balances."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.alchemy_service import AlchemyConfigError, alchemy_api_key
from app.crypto_sync import create_wallet, sync_crypto_wallets, wipe_wallet
from app.database import get_db
from app.errors import log_and_raise
from app.models import CryptoWallet
from app import app_config

router = APIRouter(prefix="/crypto", tags=["crypto"])


class HoldingOut(BaseModel):
    symbol: str
    contract_address: str
    decimals: int
    balance: float
    usd_value: float


class WalletOut(BaseModel):
    id: int
    address: str
    label: Optional[str]
    chain: str
    usd_total: float
    last_synced_at: Optional[str]
    last_error: Optional[str]
    holdings: list[HoldingOut]


class WalletsResponse(BaseModel):
    wallets: list[WalletOut]
    alchemy_configured: bool


class AddWalletRequest(BaseModel):
    address: str = Field(..., min_length=42, max_length=42)
    label: Optional[str] = None


class RefreshResponse(BaseModel):
    synced: int
    failed: int
    skipped: bool = False
    reason: Optional[str] = None
    message: str


class AlchemyConfigResponse(BaseModel):
    configured: bool


class AlchemyConfigUpdate(BaseModel):
    # Blank/omitted keeps the stored key (same convention as Plaid/Resend BYOK).
    api_key: Optional[str] = None


@router.get("/alchemy-config", response_model=AlchemyConfigResponse)
async def get_alchemy_config():
    return AlchemyConfigResponse(configured=alchemy_api_key() is not None)


@router.put("/alchemy-config", response_model=AlchemyConfigResponse)
async def update_alchemy_config(req: AlchemyConfigUpdate, db: Session = Depends(get_db)):
    try:
        if req.api_key:  # only overwrite when a non-empty key is provided
            app_config.set(db, app_config.ALCHEMY_API_KEY, req.api_key.strip(), secret=True)
        return AlchemyConfigResponse(configured=alchemy_api_key() is not None)
    except Exception as e:
        log_and_raise(e, status_code=400)


def _wallet_out(wallet: CryptoWallet) -> WalletOut:
    account = wallet.account
    usd_total = float(account.current_balance or 0) if account else 0.0
    holdings = [
        HoldingOut(
            symbol=h.symbol,
            contract_address=h.contract_address or "",
            decimals=h.decimals,
            balance=float(h.balance or 0),
            usd_value=float(h.usd_value or 0),
        )
        for h in sorted(wallet.holdings, key=lambda x: -float(x.usd_value or 0))
    ]
    return WalletOut(
        id=wallet.id,
        address=wallet.address,
        label=wallet.label,
        chain=wallet.chain,
        usd_total=usd_total,
        last_synced_at=wallet.last_synced_at.isoformat() if wallet.last_synced_at else None,
        last_error=wallet.last_error,
        holdings=holdings,
    )


@router.get("/wallets", response_model=WalletsResponse)
async def list_wallets(db: Session = Depends(get_db)):
    try:
        wallets = (
            db.query(CryptoWallet)
            .options(joinedload(CryptoWallet.holdings), joinedload(CryptoWallet.account))
            .filter(CryptoWallet.user_id == 1)
            .order_by(CryptoWallet.id.asc())
            .all()
        )
        return WalletsResponse(
            wallets=[_wallet_out(w) for w in wallets],
            alchemy_configured=alchemy_api_key() is not None,
        )
    except Exception as e:
        log_and_raise(e)


@router.post("/wallets", response_model=WalletOut)
async def add_wallet(body: AddWalletRequest, db: Session = Depends(get_db)):
    try:
        wallet = create_wallet(
            db,
            address=body.address,
            label=body.label,
            user_id=1,
        )
        wallet = (
            db.query(CryptoWallet)
            .options(joinedload(CryptoWallet.holdings), joinedload(CryptoWallet.account))
            .filter(CryptoWallet.id == wallet.id)
            .one()
        )
        return _wallet_out(wallet)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log_and_raise(e)


@router.delete("/wallets/{wallet_id}")
async def delete_wallet(wallet_id: int, db: Session = Depends(get_db)):
    try:
        wipe_wallet(db, wallet_id, user_id=1)
        return {"ok": True}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        log_and_raise(e)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_wallets(db: Session = Depends(get_db)):
    if not alchemy_api_key():
        raise HTTPException(
            status_code=503,
            detail="Alchemy is not configured. Add your Alchemy API key in Settings → Crypto wallets.",
        )
    try:
        stats = sync_crypto_wallets(db, user_id=1)
        if stats.get("skipped"):
            raise AlchemyConfigError(stats.get("reason") or "Alchemy API key not set")
        parts = [f"Synced {stats['synced']} wallet(s)"]
        if stats["failed"]:
            parts.append(f"{stats['failed']} failed")
        return RefreshResponse(
            synced=stats["synced"],
            failed=stats["failed"],
            skipped=False,
            message=", ".join(parts),
        )
    except AlchemyConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        log_and_raise(e)
