"""
Backfills/updates app.models.MarketPrice for every ticker we need daily price
history for: held securities' ticker_symbol (equities/ETFs/crypto currently in
a Holding) plus the fixed benchmark tickers (SPY, BTC-USD) used by
risk_service.py for beta. Called nightly by the scheduler (app/scheduler.py)
and safe to call more often — it only fetches the gap since the last stored
price per ticker.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Holding, MarketPrice, Security
from app.price_provider import fetch_daily_closes

BENCHMARK_TICKERS = ["SPY", "BTC-USD"]
BACKFILL_DAYS = 1100  # ~3yr so fresh installs / new tickers have room past a 1yr lookback (optimizer, beta)


def tickers_needing_sync(db: Session) -> list[str]:
    held = (
        db.query(Security.ticker_symbol)
        .join(Holding, Holding.security_id == Security.id)
        .filter(
            Security.ticker_symbol.isnot(None),
            Security.is_cash_equivalent.is_(False),
        )
        .distinct()
        .all()
    )
    tickers = {row[0] for row in held if row[0]}
    tickers.update(BENCHMARK_TICKERS)
    return sorted(tickers)


def _last_price_date(db: Session, ticker: str) -> date | None:
    row = (
        db.query(MarketPrice.price_date)
        .filter(MarketPrice.ticker == ticker)
        .order_by(MarketPrice.price_date.desc())
        .first()
    )
    return row[0] if row else None


def sync_market_prices(db: Session) -> dict:
    """Fetch and upsert missing daily closes for every held + benchmark ticker.
    Returns {"tickers_synced": int, "rows_upserted": int}."""
    tickers = tickers_needing_sync(db)
    if not tickers:
        return {"tickers_synced": 0, "rows_upserted": 0}

    today = date.today()
    last_dates = {ticker: _last_price_date(db, ticker) for ticker in tickers}
    starts = [
        (last_dates[t] + timedelta(days=1)) if last_dates[t] else (today - timedelta(days=BACKFILL_DAYS))
        for t in tickers
    ]
    earliest_start = min(starts)
    if earliest_start > today:
        return {"tickers_synced": len(tickers), "rows_upserted": 0}

    by_ticker = fetch_daily_closes(tickers, start=earliest_start, end=today + timedelta(days=1))

    rows_upserted = 0
    for ticker in tickers:
        cutoff = last_dates[ticker]
        for price_date, close_price in by_ticker.get(ticker, []):
            if cutoff and price_date <= cutoff:
                continue
            db.add(MarketPrice(ticker=ticker, price_date=price_date, close_price=close_price))
            rows_upserted += 1
    db.commit()
    return {"tickers_synced": len(tickers), "rows_upserted": rows_upserted}
