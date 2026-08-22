from __future__ import annotations

import json
import os
from datetime import date, timedelta
from decimal import Decimal

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import (  # noqa: E402
    Account,
    Base,
    Holding,
    Item,
    MarketPrice,
    SectorConstraint,
    Security,
    TickerClassification,
    User,
)


@pytest.fixture()
def memdb(tmp_path, monkeypatch):
    from app import database

    engine = create_engine(
        f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    yield TestSession


@pytest.fixture()
def client(memdb):
    import main
    from app import database
    from app.auth import require_auth
    from fastapi.testclient import TestClient

    main.app.dependency_overrides[require_auth] = lambda: 1

    def _get_db():
        s = memdb()
        try:
            yield s
        finally:
            s.close()
    main.app.dependency_overrides[database.get_db] = _get_db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_get_risk_metrics_with_no_data_returns_nulls(client):
    resp = client.get("/api/investments/risk/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["volatility_pct"] is None
    assert body["data_points"] == 0
    assert body["lookback_days"] == 365


def test_get_risk_metrics_respects_lookback_days_param(client):
    resp = client.get("/api/investments/risk/metrics?lookback_days=90")
    assert resp.status_code == 200
    assert resp.json()["lookback_days"] == 90


def test_get_risk_metrics_rejects_out_of_range_lookback(client):
    resp = client.get("/api/investments/risk/metrics?lookback_days=5")
    assert resp.status_code == 422


def test_get_optimization_with_no_holdings_returns_insufficient_data(client, db_session):
    # Advanced mode must be on to reach the insufficient-data path at all --
    # off (the default) returns the disabled result instead, which is a
    # different case (see test_get_optimization_disabled_toggle_returns_empty_result).
    db_session.query(User).filter_by(id=1).one().optimization_advanced_enabled = True
    db_session.commit()

    resp = client.get("/api/investments/risk/optimize")
    assert resp.status_code == 200
    body = resp.json()
    assert body["insufficient_data"] is True
    assert body["tickers"] == []


def test_get_optimization_disabled_toggle_returns_empty_result(client, db_session):
    # optimization_advanced_enabled defaults to False -- there is no
    # separate "basic" engine underneath it, so off means no optimizer
    # output at all, distinct from insufficient_data (which means the
    # engine ran and didn't have enough data).
    resp = client.get("/api/investments/risk/optimize")
    assert resp.status_code == 200
    body = resp.json()
    assert body["advanced_enabled"] is False
    assert body["insufficient_data"] is False
    assert body["tickers"] == []
    assert body["objectives"] == []


def test_get_optimization_rejects_out_of_range_lookback(client):
    resp = client.get("/api/investments/risk/optimize?lookback_days=10")
    assert resp.status_code == 422


@pytest.fixture()
def db_session(memdb):
    """A Session bound to the SAME engine `client`'s per-request sessions use
    (both ultimately come from `memdb`'s sessionmaker over one shared SQLite
    file) -- so data seeded/committed here is visible to `client`'s HTTP
    requests, and vice versa. Seeds the baseline User(id=1) row every
    optimization code path past the insufficient-data early-returns requires
    (build_optimization_suggestion does `db.query(User).filter_by(id=1).one()`
    unconditionally once it has >= 2 priceable tickers). Mirrors
    test_optimization_service.py's db_session fixture, rewired to reuse
    memdb's engine instead of creating its own."""
    session = memdb()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


# Mirrors test_optimization_service.py's _GOOD_TICKERS/_FLAT_TICKERS: enough
# tickers (12) that the default 10% position cap stays binding rather than
# being auto-relaxed away by relax_position_cap_if_needed (which only kicks
# in below n=11 at a 10% cap). See that file's seeded_price_history
# docstring for the full empirical rationale (correlation structure, why the
# cap binds on specific flat tickers rather than the "good" ones, etc.).
_GOOD_TICKERS = ["TICKG1", "TICKG2"]
_FLAT_TICKERS = [f"TICKF{i:02d}" for i in range(1, 11)]


@pytest.fixture()
def seeded_price_history(db_session):
    """Seeds db_session with a 12-ticker portfolio (2 steady-uptrend 'good'
    tickers + 10 flat/oscillating tickers) and 60 days of overlapping
    MarketPrice history for all of them, plus SPY (advanced mode's
    market-implied-risk-aversion benchmark -- always fetched once past the
    insufficient-data checks, regardless of whether SPY itself is held).
    Ported from test_optimization_service.py's fixture of the same
    name/shape so endpoint-level and service-level tests exercise an
    identical scenario; see that file for the full per-ticker rationale."""
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment", current_balance=Decimal("12000"))
    db_session.add(account)
    db_session.flush()

    tickers = _GOOD_TICKERS + _FLAT_TICKERS
    securities = {t: Security(plaid_security_id=f"sec-{t}", ticker_symbol=t, type="equity") for t in tickers}
    db_session.add_all(securities.values())
    db_session.flush()

    for t in tickers:
        db_session.add(Holding(account_id=account.id, security_id=securities[t].id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))

    start = date.today() - timedelta(days=60)
    for i in range(60):
        day = start + timedelta(days=i)
        for j, t in enumerate(_GOOD_TICKERS):
            price = 100 + i * (0.5 + 0.1 * j)
            db_session.add(MarketPrice(ticker=t, price_date=day, close_price=Decimal(str(price))))
        for k, t in enumerate(_FLAT_TICKERS):
            sign = 1 if (i + k) % 2 == 0 else -1
            price = 100 + sign * (4 + k % 3)
            db_session.add(MarketPrice(ticker=t, price_date=day, close_price=Decimal(str(price))))
        db_session.add(MarketPrice(ticker="SPY", price_date=day, close_price=Decimal(str(400 + i * 0.3 + (3 if i % 2 == 0 else -3)))))
    db_session.commit()
    return tickers


# Mirrors test_optimization_service.py's _SECTOR_BY_TICKER/_ETF_TICKER: same
# sector assignments and ETF choice, for the same reasons documented there
# (sectors deliberately span alphabetically before/after "healthcare" to
# guard against a late-binding-closure bug in the per-sector constraint
# loop; TICKF10 is the sole ETF so the Black-Litterman absolute-view path
# actually executes rather than trivially no-op'ing).
_SECTOR_BY_TICKER = {
    "TICKG1": "technology",
    "TICKG2": "financials",
    "TICKF01": "consumerstaples",
    "TICKF02": "industrials",
    "TICKF03": "realestate",
    "TICKF04": "utilities",
    "TICKF05": "materials",
    "TICKF06": "healthcare",
    "TICKF07": "communication",
    "TICKF08": "energy",
    "TICKF09": "consumerdiscretionary",
}
_ETF_TICKER = "TICKF10"


@pytest.fixture()
def seeded_ticker_classifications(db_session, seeded_price_history):
    """TickerClassification rows for every ticker seeded_price_history
    creates. Ported from test_optimization_service.py's fixture of the same
    name/shape -- see that file's _SECTOR_BY_TICKER docstring for the
    reasoning behind the ETF choice, sector assignments, and market-cap
    weighting."""
    classifications = [
        TickerClassification(
            ticker=_ETF_TICKER,
            asset_class="etf",
            sector_weights_json=json.dumps({"technology": 0.4, "financials": 0.3, "utilities": 0.3}),
            market_cap_or_aum=Decimal("6000000000"),
        ),
    ]
    for i, (ticker, sector) in enumerate(_SECTOR_BY_TICKER.items()):
        classifications.append(
            TickerClassification(
                ticker=ticker,
                asset_class="equity",
                sector_weights_json=json.dumps({sector: 1.0}),
                market_cap_or_aum=Decimal(str(5_000_000_000 + i * 300_000_000)),
            )
        )
    db_session.add_all(classifications)
    db_session.commit()
    return classifications


def test_optimize_endpoint_advanced_mode_shape_without_cap_relax(client, db_session, seeded_price_history, seeded_ticker_classifications):
    # 12 tickers x the default 10% cap is comfortably unrelaxed (relax_
    # position_cap_if_needed only kicks in below n=11 at a 10% cap) -- this
    # confirms cap_relaxed's ordinary "nothing to relax" happy path
    # round-trips through ClipLogEntry as None correctly, complementing the
    # real auto-relax scenario exercised below.
    db_session.query(User).filter_by(id=1).one().optimization_advanced_enabled = True
    db_session.commit()

    response = client.get("/api/investments/risk/optimize")
    assert response.status_code == 200
    body = response.json()
    assert body["advanced_enabled"] is True
    assert {o["name"] for o in body["objectives"]} == {"max_sharpe", "max_quadratic_utility"}
    for obj in body["objectives"]:
        assert len(obj["tickers"]) == 12
    assert body["cap_relaxed"] is None


def test_optimize_endpoint_advanced_mode_shape(client, db_session, seeded_price_history, seeded_ticker_classifications):
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    # Deliberately below the (1/12)/0.95 ~= 8.77% feasibility floor for 12
    # tickers, so relax_position_cap_if_needed's real auto-relax branch
    # fires -- exercising cap_relaxed's non-None dict-to-ClipLogEntry
    # conversion end-to-end through the HTTP response, not just the None
    # happy path already covered by the basic-mode test above.
    user.optimization_position_cap_pct = 5.0
    db_session.commit()
    # A sector with zero exposure among any held/classified ticker (no
    # ticker's TickerClassification.sector_weights_json mentions it), so
    # clip_sector_bounds's "constrained sector absent from the exposure
    # matrix" branch fires deterministically (clipped_to always 0.0)
    # regardless of exact achievable-weight arithmetic -- exercising
    # clip_log's real auto-clip path end-to-end through the HTTP response.
    db_session.add(SectorConstraint(user_id=1, sector="unheldsector", floor_pct=5.0, cap_pct=50.0))
    db_session.commit()

    response = client.get("/api/investments/risk/optimize")
    assert response.status_code == 200
    body = response.json()
    assert body["advanced_enabled"] is True
    assert {o["name"] for o in body["objectives"]} == {"max_sharpe", "max_quadratic_utility"}
    for obj in body["objectives"]:
        assert set(obj.keys()) == {"name", "tickers", "expected_return_pct", "volatility_pct", "sharpe"}
        assert len(obj["tickers"]) == 12
        for tw in obj["tickers"]:
            assert set(tw.keys()) == {"ticker", "current_weight_pct", "suggested_weight_pct"}

    assert isinstance(body["frontier_points"], list)
    assert len(body["frontier_points"]) > 0
    for point in body["frontier_points"]:
        assert set(point.keys()) == {"volatility_pct", "return_pct"}

    assert isinstance(body["random_portfolios"], list)
    assert len(body["random_portfolios"]) > 0
    for point in body["random_portfolios"]:
        assert set(point.keys()) == {"volatility_pct", "return_pct", "sharpe"}

    assert body["sector_breakdown"] is not None
    assert len(body["sector_breakdown"]) > 0
    for row in body["sector_breakdown"]:
        assert set(row.keys()) == {"sector", "weight_pct", "floor_pct", "cap_pct"}

    # Real auto-relax scenario (not the None happy path).
    assert body["cap_relaxed"] is not None
    assert body["cap_relaxed"]["requested_cap"] == pytest.approx(0.05)
    assert body["cap_relaxed"]["relaxed_to"] == pytest.approx((1 / 12) / 0.95)
    assert body["cap_relaxed"]["reason"] == "too few holdings for cap"

    # Real auto-clip scenario (not the empty-list happy path).
    assert len(body["clip_log"]) >= 1
    clip_entry = next(e for e in body["clip_log"] if e["sector"] == "unheldsector")
    assert clip_entry["requested_floor"] == pytest.approx(0.05)
    assert clip_entry["clipped_to"] == pytest.approx(0.0)
