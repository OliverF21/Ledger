# backend/tests/test_mcp_portfolio_optimization.py
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal

from cryptography.fernet import Fernet

# mcp_server.server imports app.services.optimization_service, which imports
# get_cached_risk_free_rate -> app_config -> app.security, which raises at
# import time if ENCRYPTION_KEY is unset. Match the same workaround used by
# other tests that transitively touch app.security (e.g.
# tests/test_optimization_service.py) so this file passes when run
# standalone, not just as part of the full suite.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.models import (  # noqa: E402
    Account,
    Base,
    Holding,
    Item,
    MarketPrice,
    Security,
    TickerClassification,
    User,
)
from mcp_server import server as mcp_server_module  # noqa: E402


@pytest.fixture
def db_session(tmp_path) -> Session:
    db_path = tmp_path / "test-optimization.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def patch_ledger_session(db_session, monkeypatch):
    """Mirrors test_mcp_spending.py's fake_ledger_session pattern (see
    test_database_diagnostics_reports_active_paths_and_counts /
    test_chart_cash_flow_returns_inline_svg_image there): redirect the MCP
    server's read-only ledger_session() to yield this test's db_session
    instead of opening the real ledger.db."""

    @contextmanager
    def fake_ledger_session():
        yield db_session

    monkeypatch.setattr(mcp_server_module, "ledger_session", fake_ledger_session)


def _seed_two_ticker_portfolio(
    db: Session, *, with_spy: bool = False, classify_ticka_as_technology: bool = False
) -> None:
    """Two-ticker brokerage holding with 60 days of overlapping MarketPrice
    history -- enough to clear build_optimization_suggestion's
    MIN_LOOKBACK_ROWS (30) with >= 2 priceable tickers. Mirrors
    test_optimization_service.py's _setup_two_ticker_portfolio (the
    service's own proven-good fixture shape), adapted here rather than
    imported cross-file since this suite owns its MCP-layer db_session
    fixture per the mcp_server test pattern (Step 2). Optionally adds SPY
    history (advanced mode's benchmark ticker, always synced per
    price_sync_service.py's BENCHMARK_TICKERS) and a TickerClassification
    for TICKA so advanced mode's sector_breakdown comes back non-empty.
    """
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db.add(item)
    db.flush()
    account = Account(
        item_id=item.id,
        plaid_account_id="acc-1",
        name="Brokerage",
        type="investment",
        current_balance=Decimal("2000"),
    )
    db.add(account)
    db.flush()

    sec_a = Security(plaid_security_id="sec-A", ticker_symbol="TICKA", type="equity")
    sec_b = Security(plaid_security_id="sec-B", ticker_symbol="TICKB", type="equity")
    db.add_all([sec_a, sec_b])
    db.flush()

    db.add(Holding(account_id=account.id, security_id=sec_a.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))
    db.add(Holding(account_id=account.id, security_id=sec_b.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))

    if classify_ticka_as_technology:
        db.add(
            TickerClassification(
                ticker="TICKA",
                asset_class="equity",
                sector_weights_json=json.dumps({"technology": 1.0}),
                market_cap_or_aum=Decimal("5000000000"),
            )
        )

    start = date.today() - timedelta(days=60)
    for i in range(60):
        day = start + timedelta(days=i)
        db.add(MarketPrice(ticker="TICKA", price_date=day, close_price=Decimal(str(100 + i * 0.5))))
        db.add(MarketPrice(ticker="TICKB", price_date=day, close_price=Decimal(str(100 + (5 if i % 2 == 0 else -5)))))
        if with_spy:
            db.add(MarketPrice(ticker="SPY", price_date=day, close_price=Decimal(str(400 + i * 0.3 + (3 if i % 2 == 0 else -3)))))
    db.commit()


def test_portfolio_optimization_tool_returns_structured_result(db_session, patch_ledger_session):
    """Basic mode (User.optimization_advanced_enabled defaults to False) --
    covers the plan brief's Step 1 illustrative assertions plus the
    single-objective/no-frontier shape basic mode guarantees."""
    _seed_two_ticker_portfolio(db_session)

    result = mcp_server_module.portfolio_optimization()

    assert result.advanced_enabled is False
    assert isinstance(result.objectives, list)
    assert len(result.objectives) == 1
    assert result.objectives[0].name == "max_sharpe"
    tickers_seen = {t["ticker"] for t in result.objectives[0].tickers}
    assert tickers_seen == {"TICKA", "TICKB"}
    assert result.frontier_points is None
    assert result.sector_breakdown is None
    assert result.clip_log == []
    assert result.insufficient_data is False
    assert result.data_points == 60
    assert result.position_cap_pct > 0


def test_portfolio_optimization_tool_advanced_mode_returns_two_objectives(db_session, patch_ledger_session):
    """Advanced mode: two BL-driven objectives, a populated efficient
    frontier, and a non-empty sector breakdown."""
    _seed_two_ticker_portfolio(db_session, with_spy=True, classify_ticka_as_technology=True)
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    db_session.commit()

    result = mcp_server_module.portfolio_optimization()

    assert result.advanced_enabled is True
    names = {o.name for o in result.objectives}
    assert names == {"max_sharpe", "max_quadratic_utility"}
    assert result.frontier_points is not None
    assert len(result.frontier_points) > 0
    assert result.sector_breakdown is not None
    assert any(row["sector"] == "technology" for row in result.sector_breakdown)


def test_portfolio_optimization_tool_reports_insufficient_data_with_no_holdings(db_session, patch_ledger_session):
    """No investment holdings at all -- the tool must still return a valid
    PortfolioOptimizationResult (empty objectives), not raise."""
    result = mcp_server_module.portfolio_optimization()

    assert result.insufficient_data is True
    assert result.objectives == []
    assert result.frontier_points is None
    assert result.sector_breakdown is None
