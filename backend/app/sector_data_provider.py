"""
Thin wrapper around yfinance for per-ticker sector/asset-class/AUM lookups —
isolated here (mirrors price_provider.py's pattern) so yfinance's quirks
stay in one place. Every lookup is non-fatal: a bad ticker or an unexpected
API shape returns a result with `error` set rather than raising, so
sector_sync_service.py can skip one ticker without failing the whole sync.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yfinance as yf


@dataclass(frozen=True)
class TickerClassificationData:
    asset_class: str
    sector_weights: dict[str, float] = field(default_factory=dict)
    market_cap_or_aum: float | None = None
    error: str | None = None


def _norm_sector_name(name) -> str:
    return str(name).lower().replace("_", "").replace(" ", "").replace("-", "")


def _normalize_sector_weightings(raw) -> dict:
    """funds_data.sector_weightings shape has varied across yfinance
    versions (dict, list of single-key dicts, Series) — handle all three.
    Confirmed against live VOO/GLD lookups on yfinance==1.6.0 (the version
    installed against requirements.txt's `yfinance>=0.2.40` floor at the
    time this was written): it's a plain dict, e.g. {'technology': 0.3861,
    ...}, so the dict branch below is the one that actually fires today;
    the list/Series branches are defensive for other yfinance versions."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, (list, tuple)):
        items = [kv for item in raw if isinstance(item, dict) for kv in item.items()]
    else:
        try:
            items = raw.squeeze().to_dict().items()
        except Exception:
            return {}
    return {_norm_sector_name(k): float(v) for k, v in items}


def fetch_ticker_classification(ticker: str) -> TickerClassificationData:
    yahoo = ticker.replace(".", "-")  # BRK.B -> BRK-B
    try:
        t = yf.Ticker(yahoo)
        info = t.info
        quote_type = (info.get("quoteType") or "").upper()

        if not quote_type:
            # Confirmed against a real delisted/nonexistent symbol: yfinance
            # 1.6.0 does NOT raise here. yf.Ticker(...) succeeds and .info
            # comes back near-empty (observed: {'trailingPegRatio': None}),
            # with no quoteType at all. Without this check that would fall
            # through to the equity branch below and silently produce an
            # empty-but-"successful" equity result instead of surfacing the
            # ticker as unresolved.
            return TickerClassificationData(
                asset_class="unknown",
                error=f"no quoteType returned for {ticker!r}; ticker may be invalid or delisted",
            )
        is_etf = quote_type == "ETF"

        if not is_etf:
            sector = info.get("sector")
            cap = t.fast_info.get("marketCap")
            return TickerClassificationData(
                asset_class="equity",
                sector_weights={_norm_sector_name(sector): 1.0} if sector else {},
                market_cap_or_aum=float(cap) if cap else None,
            )

        weightings = _normalize_sector_weightings(t.funds_data.sector_weightings)
        aum = t.fast_info.get("marketCap") or info.get("totalAssets")
        if weightings:
            return TickerClassificationData(
                asset_class="etf",
                sector_weights=weightings,
                market_cap_or_aum=float(aum) if aum else None,
            )
        # No equity sector exposure (GLD, SLV, ...) — commodities bucket
        # rather than exempting it, so it still gets its own floor/cap.
        return TickerClassificationData(
            asset_class="commodity_etf",
            sector_weights={"commodities": 1.0},
            market_cap_or_aum=float(aum) if aum else None,
        )
    except Exception as e:
        return TickerClassificationData(asset_class="unknown", error=str(e))
