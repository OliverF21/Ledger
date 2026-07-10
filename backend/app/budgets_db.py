"""
Separate SQLite database for user-editable budget data.
Isolated from ledger.db (the Plaid data dump) so AV/Defender scanning the
main DB file never blocks budget writes.
"""

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import JSON, Column, DateTime, Integer, Numeric, String, create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.sqlite_paths import resolve_sqlite_database_url

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Allow override via env; default to budgets.db alongside ledger.db in backend/
BUDGETS_DB_URL = resolve_sqlite_database_url(
    os.getenv("BUDGETS_DATABASE_URL", "sqlite:///budgets.db")
)

budgets_engine = create_engine(
    BUDGETS_DB_URL,
    poolclass=NullPool,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)


@event.listens_for(budgets_engine, "connect")
def _set_wal(dbapi_conn, _):
    try:
        dbapi_conn.execute("PRAGMA busy_timeout=30000")
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass


BudgetsBase = declarative_base()


class Budget(BudgetsBase):
    """
    Monthly spending budget. Flat table — no FK to ledger.db.
    category_key  : Plaid PFC parent key (e.g. "FOOD_AND_DRINK") used to
                    aggregate spending from transaction.category_plaid.
                    NULL for manually-named budgets.
    category_name : human-readable display label (e.g. "Food & Drink").
    """

    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, default=1)
    month = Column(String(7), nullable=False)            # YYYY-MM
    category_name = Column(String(255), nullable=False)
    category_key = Column(String(255), nullable=True)    # Plaid PFC parent key
    limit = Column(Numeric(19, 4), nullable=False)
    color = Column(String(7), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── AI advisor proposals ──────────────────────────────────────────────────────
#
# Proposals are AI-generated *intents* (e.g. "set Dining to $400"), staged here
# until the user reviews and applies them in the Advisor page. They live in
# budgets.db — NOT a third file — because they are small budget-adjacent metadata
# (same AV-scanning profile as budgets, closer to budgets than to Plaid truth)
# and a third DB would add another WAL, init, and backup target for no benefit.
#
# Hard invariant: nothing here ever touches ledger.db, and analytics never reads
# this table. The only path that mutates real budgets from a proposal is the
# Apply endpoint (routes/proposals.py), which calls the shared budget writer.

# Proposal.status lifecycle:
#   pending ──apply──▶ applied ──undo──▶ undone
#      │  └─dismiss──▶ dismissed
#      ├─(superseded by a newer pending proposal)──▶ superseded
#      └─(scheduler sweep, age > TTL)──▶ expired
PROPOSAL_STATUSES = ("pending", "applied", "dismissed", "undone", "superseded", "expired")


class Proposal(BudgetsBase):
    """
    An AI-generated, user-reviewable change intent. Flat table, no FK to
    ledger.db. `payload` holds the kind-specific request; `undo` captures the
    prior state at apply time so the change is reversible.

    For kind="set_budget", payload is:
      {payload_version, month, category_key, category_name, limit,
       basis_limit, color}
    and undo is:
      {budget_id, prev_limit, budget_existed, applied_limit}
    """

    __tablename__ = "proposals"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, default=1)
    kind = Column(String(64), nullable=False)             # e.g. "set_budget"
    status = Column(String(32), nullable=False, default="pending")
    source = Column(String(64), nullable=False, default="claude")
    payload = Column(JSON, nullable=False)
    rationale = Column(String, nullable=True)             # Claude's explanation
    undo = Column(JSON, nullable=True)                    # prior state, set at apply
    superseded_by = Column(Integer, nullable=True)        # id of newer pending proposal
    created_at = Column(DateTime, default=datetime.utcnow)
    applied_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    undone_at = Column(DateTime, nullable=True)


BudgetsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=budgets_engine)


def init_budgets_db():
    """Create the budgets + proposals tables if they don't exist yet."""
    BudgetsBase.metadata.create_all(bind=budgets_engine)


def get_budgets_db() -> Session:
    """FastAPI dependency: yields a session for budgets.db."""
    db = BudgetsSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Proposals share budgets.db, so they share the same session/engine. A distinct
# dependency name keeps call sites self-documenting.
get_proposals_db = get_budgets_db
