"""
3-month Treasury yield (FRED series DGS3MO), used as the risk-free rate input
to Sharpe ratio / max-Sharpe optimization. FRED publishes this series as a
public CSV with no API key required, so we fetch it directly rather than
adding an API-key dependency for a single slow-moving number.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from app import app_config

logger = logging.getLogger(__name__)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
DEFAULT_RISK_FREE_RATE_PCT = 5.0  # fallback if FRED is unreachable and no cached value exists
RISK_FREE_RATE_PCT = "RISK_FREE_RATE_PCT"
RISK_FREE_RATE_FETCHED_AT = "RISK_FREE_RATE_FETCHED_AT"


def parse_fred_csv(text: str) -> float | None:
    """Return the most recent non-missing (FRED marks gaps as '.') DGS3MO value, or None."""
    reader = csv.DictReader(io.StringIO(text))
    latest: float | None = None
    for row in reader:
        raw = row.get("DGS3MO", ".")
        if raw and raw != ".":
            try:
                latest = float(raw)
            except ValueError:
                continue
    return latest


def fetch_and_cache_risk_free_rate(db: Session) -> float:
    """
    Fetch the latest 3-month T-bill yield from FRED and cache it in app_config
    so a transient network failure doesn't block risk-metric calculations.
    Called from the nightly scheduler job (Task 5) — reads should go through
    get_cached_risk_free_rate() instead.
    """
    try:
        response = requests.get(FRED_CSV_URL, timeout=10)
        response.raise_for_status()
        rate = parse_fred_csv(response.text)
    except Exception as e:
        logger.error(f"Failed to fetch risk-free rate from FRED: {str(e)}")
        rate = None

    if rate is not None:
        app_config.set(db, RISK_FREE_RATE_PCT, str(rate))
        app_config.set(db, RISK_FREE_RATE_FETCHED_AT, datetime.utcnow().isoformat())
    return get_cached_risk_free_rate(db)


def get_cached_risk_free_rate(db: Session) -> float:
    """Read the cached risk-free rate, falling back to DEFAULT_RISK_FREE_RATE_PCT
    if nothing has been fetched yet."""
    raw = app_config.get(db, RISK_FREE_RATE_PCT)
    if raw is None:
        return DEFAULT_RISK_FREE_RATE_PCT
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_RISK_FREE_RATE_PCT
