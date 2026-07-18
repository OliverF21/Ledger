"""Curated ERC-20 allowlist for Robinhood Chain crypto wallet sync.

Only tokens with verified contract addresses on chain 4663 are listed.
USDG is priced at $1; others use Alchemy Prices when available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PricingRule = Literal["stable_usd", "alchemy_price", "native_eth"]

CHAIN_ID = 4663
CHAIN_KEY = "robinhood-mainnet"
CRYPTO_ITEM_ID = "crypto_wallets"


@dataclass(frozen=True)
class TokenSpec:
    symbol: str
    contract_address: str | None  # None = native ETH
    decimals: int
    pricing: PricingRule


# Official RH-chain contracts: https://docs.robinhood.com/chain/contracts/
# USDG: https://docs.paxos.com/guides/stablecoin/usdg/mainnet
ROBINHOOD_TOKEN_ALLOWLIST: tuple[TokenSpec, ...] = (
    TokenSpec(
        symbol="USDG",
        contract_address="0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
        decimals=6,
        pricing="stable_usd",
    ),
    TokenSpec(
        symbol="WETH",
        contract_address="0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73",
        decimals=18,
        pricing="alchemy_price",
    ),
    TokenSpec(
        symbol="ETH",
        contract_address=None,
        decimals=18,
        pricing="native_eth",
    ),
)

# Items that must never be synced via Plaid (empty / non-Plaid access tokens).
PLAID_SYNC_EXCLUDED_ITEMS = frozenset({"manual_import", "test_item", CRYPTO_ITEM_ID})
