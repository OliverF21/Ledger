"""Tests for read-only crypto wallet sync → net worth."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.alchemy_service import normalize_address
from app.crypto_sync import create_wallet, get_or_create_crypto_item, wipe_wallet
from app.crypto_tokens import CRYPTO_ITEM_ID, PLAID_SYNC_EXCLUDED_ITEMS
from app.models import Account, BalanceSnapshot, Base, CryptoHolding, CryptoWallet, Item, User
from app.services.analytics_service import build_net_worth
from app.sync_engine import get_real_items


@pytest.fixture
def db_session(tmp_path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'crypto-test.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_normalize_address_accepts_valid():
    assert normalize_address("0xAbCDEF0123456789AbCDEF0123456789AbCDEF01") == (
        "0xabcdef0123456789abcdef0123456789abcdef01"
    )


def test_normalize_address_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_address("not-an-address")
    with pytest.raises(ValueError):
        normalize_address("0x123")


def test_get_real_items_excludes_crypto_item(db_session: Session):
    plaid = Item(
        user_id=1,
        item_id="plaid_item",
        institution_name="Bank",
        access_token_encrypted="enc",
    )
    crypto = get_or_create_crypto_item(db_session)
    db_session.add(plaid)
    db_session.commit()

    real = get_real_items(db_session)
    assert CRYPTO_ITEM_ID in PLAID_SYNC_EXCLUDED_ITEMS
    assert {i.item_id for i in real} == {"plaid_item"}
    assert crypto.item_id == CRYPTO_ITEM_ID


def test_sync_wallet_updates_account_and_snapshot(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "test-key")

    fake_rows = [
        {
            "symbol": "USDG",
            "contract_address": "0x5fc5360d0400a0fd4f2af552add042d716f1d168",
            "decimals": 6,
            "raw_balance": 1_500_000_000,  # 1500 USDG
            "balance": Decimal("1500"),
            "usd_price": Decimal("1"),
            "usd_value": Decimal("1500.0000"),
        },
        {
            "symbol": "ETH",
            "contract_address": "",
            "decimals": 18,
            "raw_balance": 0,
            "balance": Decimal("0"),
            "usd_price": Decimal("0"),
            "usd_value": Decimal("0"),
        },
    ]

    with patch("app.crypto_sync.fetch_allowlisted_balances", return_value=fake_rows):
        wallet = create_wallet(db_session, address="0xabcdef0123456789abcdef0123456789abcdef01", label="RH")

    db_session.refresh(wallet)
    account = db_session.query(Account).filter(Account.id == wallet.account_id).one()
    assert float(account.current_balance) == 1500.0
    assert account.type == "crypto"
    assert account.name == "RH"

    holdings = db_session.query(CryptoHolding).filter(CryptoHolding.wallet_id == wallet.id).all()
    assert len(holdings) == 1
    assert holdings[0].symbol == "USDG"
    assert float(holdings[0].usd_value) == 1500.0

    snap = (
        db_session.query(BalanceSnapshot)
        .filter(BalanceSnapshot.account_id == account.id, BalanceSnapshot.snapshot_date == date.today())
        .one()
    )
    assert float(snap.balance) == 1500.0


def test_build_net_worth_includes_crypto_account(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "test-key")
    fake_rows = [
        {
            "symbol": "USDG",
            "contract_address": "0x5fc5360d0400a0fd4f2af552add042d716f1d168",
            "decimals": 6,
            "raw_balance": 200_000_000,
            "balance": Decimal("200"),
            "usd_price": Decimal("1"),
            "usd_value": Decimal("200.0000"),
        },
    ]
    with patch("app.crypto_sync.fetch_allowlisted_balances", return_value=fake_rows):
        create_wallet(db_session, address="0x1111111111111111111111111111111111111111")

    # Also add a normal bank account so NW isn't only crypto
    user_item = Item(
        user_id=1,
        item_id="bank",
        institution_name="Bank",
        access_token_encrypted="x",
    )
    checking = Account(
        item=user_item,
        plaid_account_id="chk",
        name="Checking",
        type="depository",
        subtype="checking",
        current_balance=Decimal("1000"),
    )
    db_session.add_all([user_item, checking])
    db_session.commit()

    result = build_net_worth(db_session, months=6)
    assert result.current_net_worth == 1200.0
    assert any(a.type == "crypto" for a in result.accounts)


def test_create_wallet_rejects_duplicate(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "test-key")
    addr = "0x2222222222222222222222222222222222222222"
    with patch("app.crypto_sync.fetch_allowlisted_balances", return_value=[]):
        create_wallet(db_session, address=addr)
        with pytest.raises(ValueError, match="already added"):
            create_wallet(db_session, address=addr)


def test_wipe_wallet_removes_account_and_snapshots(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "test-key")
    fake_rows = [
        {
            "symbol": "USDG",
            "contract_address": "0x5fc5360d0400a0fd4f2af552add042d716f1d168",
            "decimals": 6,
            "raw_balance": 1_000_000,
            "balance": Decimal("1"),
            "usd_price": Decimal("1"),
            "usd_value": Decimal("1.0000"),
        },
    ]
    with patch("app.crypto_sync.fetch_allowlisted_balances", return_value=fake_rows):
        wallet = create_wallet(db_session, address="0x3333333333333333333333333333333333333333")

    account_id = wallet.account_id
    wallet_id = wallet.id
    wipe_wallet(db_session, wallet_id)

    assert db_session.query(CryptoWallet).filter(CryptoWallet.id == wallet_id).first() is None
    assert db_session.query(CryptoHolding).filter(CryptoHolding.wallet_id == wallet_id).count() == 0
    assert db_session.query(Account).filter(Account.id == account_id).first() is None
    assert db_session.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == account_id).count() == 0


def test_sync_without_api_key_sets_error(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ALCHEMY_API_KEY", raising=False)
    # create_wallet without key still saves the wallet
    with patch("app.crypto_sync.fetch_allowlisted_balances") as mock_fetch:
        wallet = create_wallet(db_session, address="0x4444444444444444444444444444444444444444")
        mock_fetch.assert_not_called()

    db_session.refresh(wallet)
    assert wallet.last_error is not None
    assert "Alchemy" in wallet.last_error


def test_alchemy_api_key_reads_app_config(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Desktop BYOK: app_config takes precedence over env."""
    monkeypatch.delenv("ALCHEMY_API_KEY", raising=False)
    from app import app_config
    from app.alchemy_service import alchemy_api_key
    from app import database as database_mod

    monkeypatch.setattr(database_mod, "SessionLocal", lambda: db_session)
    app_config.set(db_session, app_config.ALCHEMY_API_KEY, "byok-test-key", secret=True)
    assert alchemy_api_key() == "byok-test-key"
