# backend/backfill_transfer_matches.py
"""
One-off backfill: run the cross-account transfer matcher
(app.transfer_matcher) against a user's entire existing transaction
history, not just the small lookback window used during normal incremental
syncs. Run once after deploying the transfer-matching feature; safe to
re-run (idempotent — only touches unmatched rows).

Run from backend/ with the venv active:
    python backfill_transfer_matches.py                       # backend/ledger.db
    LEDGER_USE_APPDATA=1 python backfill_transfer_matches.py  # desktop app's DB (must be closed first)
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap_desktop

bootstrap_desktop()

from app.database import SessionLocal
from app.models import Transaction
from app.transfer_matcher import match_transfers


def compute_lookback_days(db: Session, *, today: date | None = None) -> int:
    """Days between the earliest non-removed transaction and today, so the
    matcher's lookback window covers the user's entire synced history."""
    today = today or date.today()
    earliest = db.query(func.min(Transaction.date)).filter(Transaction.removed.is_(False)).scalar()
    if earliest is None:
        return 0
    return (today - earliest).days + 1


def main() -> None:
    db = SessionLocal()
    try:
        lookback_days = compute_lookback_days(db)
        if lookback_days <= 0:
            print("No transactions found; nothing to backfill.")
            return
        stats = match_transfers(db, lookback_days=lookback_days)
        print(
            f"Backfilled transfer matches: {stats['transfer_pairs']} transfer pair(s), "
            f"{stats['investment_pairs']} investment pair(s) (lookback={lookback_days} days)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
