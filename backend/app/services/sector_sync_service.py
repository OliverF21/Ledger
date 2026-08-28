"""
Weekly sync of TickerClassification (sector/asset-class/AUM) for every held
ticker. Mirrors price_sync_service.py's shape but on a much slower cadence —
sector/AUM data barely moves day to day, and this is the slow one-network-
call-per-ticker operation the optimizer must never do synchronously in a
request path.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Holding, Security, TickerClassification
from app.sector_data_provider import fetch_ticker_classification

STALE_AFTER_DAYS = 14


def _held_tickers(db: Session) -> set[str]:
    rows = (
        db.query(Security.ticker_symbol)
        .join(Holding, Holding.security_id == Security.id)
        .filter(Security.ticker_symbol.isnot(None), Security.is_cash_equivalent.is_(False))
        .distinct()
        .all()
    )
    return {r[0] for r in rows if r[0]}


def tickers_needing_sector_sync(db: Session) -> list[str]:
    """Held tickers with no TickerClassification row, or one older than
    STALE_AFTER_DAYS days."""
    held = _held_tickers(db)
    if not held:
        return []
    cutoff = datetime.utcnow() - timedelta(days=STALE_AFTER_DAYS)
    fresh = {
        row[0]
        for row in db.query(TickerClassification.ticker)
        .filter(TickerClassification.ticker.in_(held), TickerClassification.last_synced_at >= cutoff)
        .all()
    }
    return sorted(held - fresh)


def sync_sector_classifications(db: Session) -> dict:
    """Fetch and upsert sector/asset-class/AUM data for every ticker that
    needs it. fetch_ticker_classification() never raises (see
    sector_data_provider.py) — a failed lookup comes back as a
    TickerClassificationData with `error` set, which is still upserted (so
    the failure itself is recorded and doesn't get retried until stale
    again). Returns {"tickers_synced": int, "errors": int}, where
    tickers_synced counts every ticker attempted, success or not."""
    tickers = tickers_needing_sector_sync(db)
    if not tickers:
        return {"tickers_synced": 0, "errors": 0}

    synced, errors = 0, 0
    for ticker in tickers:
        data = fetch_ticker_classification(ticker)
        row = db.query(TickerClassification).filter_by(ticker=ticker).one_or_none()
        if row is None:
            row = TickerClassification(ticker=ticker)
            db.add(row)
        row.asset_class = data.asset_class
        row.sector_weights_json = json.dumps(data.sector_weights) if data.sector_weights else None
        row.market_cap_or_aum = data.market_cap_or_aum
        row.last_synced_at = datetime.utcnow()
        row.sync_error = data.error
        synced += 1
        if data.error:
            errors += 1
    db.commit()
    return {"tickers_synced": synced, "errors": errors}
