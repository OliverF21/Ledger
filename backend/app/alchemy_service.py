"""Alchemy RPC client for Robinhood Chain read-only balance queries.

BYOK: ALCHEMY_API_KEY is resolved via app_config (desktop Settings, encrypted
at rest) first, os.getenv fallback second — same pattern as Plaid/Resend.
"""

from __future__ import annotations

import logging
import os
import re
from decimal import Decimal
from typing import Optional

import requests

from app.crypto_tokens import CHAIN_KEY, ROBINHOOD_TOKEN_ALLOWLIST, TokenSpec

logger = logging.getLogger("ledger")

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
# balanceOf(address) selector
_BALANCE_OF_SELECTOR = "70a08231"


class AlchemyConfigError(RuntimeError):
    """Raised when ALCHEMY_API_KEY is missing."""


def _setting(name: str) -> Optional[str]:
    """Resolve Alchemy setting: app_config first, os.getenv fallback."""
    try:
        from app.database import SessionLocal
        from app import app_config

        db = SessionLocal()
        try:
            val = app_config.get(db, name)
        finally:
            db.close()
        if val:
            return val
    except Exception:
        logger.debug("app_config lookup failed for %s; falling back to env", name, exc_info=True)
    return os.getenv(name)


def alchemy_api_key() -> str | None:
    key = (_setting("ALCHEMY_API_KEY") or "").strip()
    return key or None


def require_alchemy_api_key() -> str:
    key = alchemy_api_key()
    if not key:
        raise AlchemyConfigError(
            "Alchemy is not configured. Add your Alchemy API key in Settings → Crypto wallets."
        )
    return key


def normalize_address(address: str) -> str:
    """Validate 0x + 40 hex and return lowercased form for storage uniqueness."""
    raw = (address or "").strip()
    if not _ADDRESS_RE.match(raw):
        raise ValueError("Invalid wallet address. Expected 0x followed by 40 hex characters.")
    return raw.lower()


def _rpc_url(api_key: str) -> str:
    return f"https://{CHAIN_KEY}.g.alchemy.com/v2/{api_key}"


def _rpc_call(api_key: str, method: str, params: list) -> object:
    resp = requests.post(
        _rpc_url(api_key),
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message") or str(payload["error"]))
    return payload.get("result")


def _pad_address(address: str) -> str:
    return address.lower().removeprefix("0x").zfill(64)


def erc20_balance_of(api_key: str, contract: str, wallet: str) -> int:
    data = "0x" + _BALANCE_OF_SELECTOR + _pad_address(wallet)
    result = _rpc_call(
        api_key,
        "eth_call",
        [{"to": contract, "data": data}, "latest"],
    )
    if not result or result == "0x":
        return 0
    return int(result, 16)


def native_eth_balance(api_key: str, wallet: str) -> int:
    result = _rpc_call(api_key, "eth_getBalance", [wallet, "latest"])
    if not result or result == "0x":
        return 0
    return int(result, 16)


def _alchemy_token_price_usd(api_key: str, network: str, contract: str | None) -> Decimal | None:
    """Fetch USD price via Alchemy Prices API. Returns None on failure."""
    try:
        if contract:
            body = {
                "addresses": [{"network": network, "address": contract.lower()}],
            }
            url = f"https://api.g.alchemy.com/prices/v1/{api_key}/tokens/by-address"
        else:
            # Native ETH on Robinhood Chain — price via eth-mainnet ETH as proxy
            body = {"symbols": ["ETH"]}
            url = f"https://api.g.alchemy.com/prices/v1/{api_key}/tokens/by-symbol"

        resp = requests.post(url, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        tokens = data.get("data") or data.get("tokens") or []
        if not tokens:
            return None
        prices = tokens[0].get("prices") or []
        for p in prices:
            if str(p.get("currency", "")).upper() == "USD":
                return Decimal(str(p["value"]))
        if prices:
            return Decimal(str(prices[0]["value"]))
    except Exception:
        logger.exception("Alchemy price lookup failed for %s", contract or "ETH")
    return None


def price_usd_for_token(api_key: str, spec: TokenSpec) -> Decimal:
    if spec.pricing == "stable_usd":
        return Decimal("1")
    price = _alchemy_token_price_usd(api_key, CHAIN_KEY, spec.contract_address)
    if price is not None and price > 0:
        return price
    # WETH / native ETH: fall back to eth-mainnet ETH price if RH network price missing
    if spec.pricing in ("alchemy_price", "native_eth"):
        fallback = _alchemy_token_price_usd(api_key, "eth-mainnet", None)
        if fallback is None:
            # by-symbol path
            try:
                resp = requests.post(
                    f"https://api.g.alchemy.com/prices/v1/{api_key}/tokens/by-symbol",
                    json={"symbols": ["ETH"]},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                tokens = data.get("data") or []
                if tokens:
                    for p in tokens[0].get("prices") or []:
                        if str(p.get("currency", "")).upper() == "USD":
                            return Decimal(str(p["value"]))
            except Exception:
                logger.exception("ETH symbol price fallback failed")
        elif fallback > 0:
            return fallback
    return Decimal("0")


def fetch_allowlisted_balances(api_key: str, wallet: str) -> list[dict]:
    """
    Return allowlisted token balances for a wallet.

    Each dict: symbol, contract_address, decimals, raw_balance, balance, usd_value, usd_price
    """
    wallet = normalize_address(wallet)
    rows: list[dict] = []
    for spec in ROBINHOOD_TOKEN_ALLOWLIST:
        if spec.contract_address is None:
            raw = native_eth_balance(api_key, wallet)
            contract_key = ""
        else:
            raw = erc20_balance_of(api_key, spec.contract_address, wallet)
            contract_key = spec.contract_address.lower()

        balance = Decimal(raw) / (Decimal(10) ** spec.decimals)
        if balance == 0:
            # Still record zero rows so the UI can show tracked tokens; filter in sync if desired
            usd_price = Decimal("0")
            usd_value = Decimal("0")
        else:
            usd_price = price_usd_for_token(api_key, spec)
            usd_value = (balance * usd_price).quantize(Decimal("0.0001"))

        rows.append(
            {
                "symbol": spec.symbol,
                "contract_address": contract_key,
                "decimals": spec.decimals,
                "raw_balance": raw,
                "balance": balance,
                "usd_price": usd_price,
                "usd_value": usd_value,
            }
        )
    return rows
