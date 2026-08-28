"""Optimization preferences + sector/ticker constraint CRUD endpoint tests."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Base, User  # noqa: E402


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


@pytest.fixture()
def db_session(memdb):
    """A Session bound to the SAME engine `client`'s per-request sessions use.
    Seeds the baseline User(id=1) row that GET/PUT optimization-settings
    requires (both do `db.query(User).filter_by(id=1).one()` unconditionally).
    Mirrors test_portfolio_risk_api.py's db_session fixture."""
    session = memdb()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def auth_headers():
    """require_auth is overridden in the `client` fixture above, so the
    header content itself is never checked -- this only exists so calls
    read the same way they would against the real dependency."""
    return {"Authorization": "Bearer test-token"}


# ─── Optimization settings ─────────────────────────────────────────────────

def test_get_and_put_optimization_settings(client, db_session, auth_headers):
    response = client.get("/api/investments/optimization-settings", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["advanced_enabled"] is False
    assert body["position_cap_pct"] == 10.0
    assert body["concentration_strength"] == 0.5

    response = client.put(
        "/api/investments/optimization-settings",
        json={"advanced_enabled": True, "position_cap_pct": 15.0, "concentration_strength": 0.7},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["advanced_enabled"] is True
    assert body["position_cap_pct"] == 15.0
    assert body["concentration_strength"] == 0.7

    # Verify the change was actually persisted, not just echoed in the PUT response.
    followup = client.get("/api/investments/optimization-settings", headers=auth_headers)
    assert followup.status_code == 200
    followup_body = followup.json()
    assert followup_body["advanced_enabled"] is True
    assert followup_body["position_cap_pct"] == 15.0
    assert followup_body["concentration_strength"] == 0.7


def test_optimization_settings_rejects_out_of_range_cap_and_strength(client, auth_headers):
    cap = client.put(
        "/api/investments/optimization-settings",
        json={"position_cap_pct": 0},
        headers=auth_headers,
    )
    assert cap.status_code == 422

    strength = client.put(
        "/api/investments/optimization-settings",
        json={"concentration_strength": 1.5},
        headers=auth_headers,
    )
    assert strength.status_code == 422


def test_optimization_settings_null_coalescing_on_get_and_put(client, db_session, auth_headers):
    """Simulates a pre-existing DB row that predates the migration adding
    these columns (models.py:55-58): _ensure_columns()'s ALTER TABLE ADD
    COLUMN carries no DEFAULT clause, so real rows can have all three
    optimization_* fields NULL despite their declared ORM default=. GET must
    not 500 (float(None)/bool(None) would raise) and must fall back to the
    documented defaults; PUT must apply the same fallback when echoing back
    any field the caller didn't send this call, since the DB can still hold
    NULL for it.

    A direct ORM `user.optimization_advanced_enabled = None` write can't
    reproduce this: db_session's table was built via Base.metadata.create_all(),
    which (unlike _ensure_columns()'s bare ALTER TABLE) faithfully encodes the
    model's `nullable=False` into the actual SQLite schema, so SQLite itself
    rejects a NULL write with IntegrityError before the request ever reaches
    the route. Instead, reproduce the real mechanism directly: drop each
    column and re-add it with a bare ALTER TABLE (no NOT NULL/DEFAULT, same
    as _ensure_columns()), which converts the existing row's value to a
    genuine NULL exactly like a real upgrade would.
    """
    db_session.query(User).filter_by(id=1).one()  # sanity: row exists before the schema surgery below
    engine = db_session.get_bind()
    with engine.begin() as conn:
        for column, col_type in [
            ("optimization_advanced_enabled", "BOOLEAN"),
            ("optimization_position_cap_pct", "NUMERIC(5, 2)"),
            ("optimization_concentration_strength", "NUMERIC(3, 2)"),
        ]:
            conn.execute(text(f"ALTER TABLE users DROP COLUMN {column}"))
            conn.execute(text(f"ALTER TABLE users ADD COLUMN {column} {col_type}"))

    response = client.get("/api/investments/optimization-settings", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["advanced_enabled"] is False
    assert body["position_cap_pct"] == 10.0
    assert body["concentration_strength"] == 0.5

    # Only position_cap_pct is sent; advanced_enabled/concentration_strength
    # remain NULL in the DB and must still coalesce to their documented
    # defaults in the response rather than raising.
    response = client.put(
        "/api/investments/optimization-settings",
        json={"position_cap_pct": 20.0},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["position_cap_pct"] == 20.0
    assert body["advanced_enabled"] is False
    assert body["concentration_strength"] == 0.5


# ─── Sector constraints ─────────────────────────────────────────────────────

def test_sector_constraint_crud(client, auth_headers):
    create = client.post(
        "/api/investments/sector-constraints",
        json={"sector": "healthcare", "floor_pct": 5.0, "cap_pct": 40.0},
        headers=auth_headers,
    )
    assert create.status_code == 200
    body = create.json()
    assert body["sector"] == "healthcare"
    assert body["floor_pct"] == 5.0
    assert body["cap_pct"] == 40.0
    constraint_id = body["id"]

    listed = client.get("/api/investments/sector-constraints", headers=auth_headers)
    assert listed.status_code == 200
    assert any(c["id"] == constraint_id for c in listed.json())

    # `sector` is required by SectorConstraintPayload even on PUT (the handler
    # doesn't reassign row.sector from it -- the route is keyed by
    # constraint_id, not by sector -- but Pydantic still requires the field
    # to be present in the body for the request to validate).
    updated = client.put(
        f"/api/investments/sector-constraints/{constraint_id}",
        json={"sector": "healthcare", "floor_pct": 8.0, "cap_pct": 40.0},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["floor_pct"] == 8.0
    assert updated_body["cap_pct"] == 40.0

    # Verify the update was actually persisted, not just echoed in the PUT response.
    listed_after_update = client.get("/api/investments/sector-constraints", headers=auth_headers)
    matched = next(c for c in listed_after_update.json() if c["id"] == constraint_id)
    assert matched["floor_pct"] == 8.0

    deleted = client.delete(f"/api/investments/sector-constraints/{constraint_id}", headers=auth_headers)
    assert deleted.status_code == 200
    listed_after = client.get("/api/investments/sector-constraints", headers=auth_headers)
    assert not any(c["id"] == constraint_id for c in listed_after.json())


def test_sector_constraint_sector_name_is_normalized_server_side(client, auth_headers):
    """A sector name must be stored in the same normalized form
    sector_data_provider._norm_sector_name produces for TickerClassification's
    sector keys -- lowercased with underscores, spaces and hyphens stripped.

    clip_sector_bounds matches constraints to exposure-matrix columns by
    exact string equality, so an unnormalized name is a constraint that
    silently never applies to anything. The frontend normalizes before
    calling, but the API is reachable without it.
    """
    created = client.post(
        "/api/investments/sector-constraints",
        json={"sector": "Financial Services", "floor_pct": 5.0, "cap_pct": 40.0},
        headers=auth_headers,
    )
    assert created.status_code == 200
    assert created.json()["sector"] == "financialservices"

    # Persisted normalized, not just normalized in the echoed response.
    listed = client.get("/api/investments/sector-constraints", headers=auth_headers)
    assert [c["sector"] for c in listed.json()] == ["financialservices"]


def test_sector_constraint_duplicate_check_uses_the_normalized_name(client, auth_headers):
    """Normalization has to happen BEFORE the duplicate lookup, not just
    before the insert -- otherwise "Financial Services" and "financialservices"
    each pass the duplicate check against the raw string and both land as
    rows that are in fact the same sector."""
    first = client.post(
        "/api/investments/sector-constraints",
        json={"sector": "financialservices", "floor_pct": 5.0, "cap_pct": 40.0},
        headers=auth_headers,
    )
    assert first.status_code == 200

    dup = client.post(
        "/api/investments/sector-constraints",
        json={"sector": "Financial-Services", "floor_pct": 5.0, "cap_pct": 40.0},
        headers=auth_headers,
    )
    assert dup.status_code == 409


def test_ticker_constraint_name_is_not_normalized(client, auth_headers):
    """The sector normalization must NOT leak onto tickers: they're matched
    against synced uppercase symbols (build_ticker_bounds), a different
    convention entirely. Lowercasing "VOO" to "voo" would break exactly the
    matching it's meant to help."""
    created = client.post(
        "/api/investments/ticker-constraints",
        json={"ticker": "VOO", "floor_pct": 5.0, "cap_pct": 40.0},
        headers=auth_headers,
    )
    assert created.status_code == 200
    assert created.json()["ticker"] == "VOO"


def test_sector_constraint_duplicate_sector_returns_409(client, auth_headers):
    client.post(
        "/api/investments/sector-constraints",
        json={"sector": "energy", "floor_pct": 0.0, "cap_pct": 30.0},
        headers=auth_headers,
    )
    dup = client.post(
        "/api/investments/sector-constraints",
        json={"sector": "energy", "floor_pct": 0.0, "cap_pct": 30.0},
        headers=auth_headers,
    )
    assert dup.status_code == 409


@pytest.mark.parametrize("method", ["post", "put"])
def test_sector_constraint_rejects_floor_above_cap(client, auth_headers, method):
    """floor_pct > cap_pct must be a 422, never a 200 (which would persist a
    row that later crashes the solve) and never a 500.

    Without the payload validator this pair reaches
    scipy.optimize.minimize's `bounds` as (lower=0.40, upper=0.02), which
    scipy rejects with `ValueError: An upper bound is less than the
    corresponding lower bound` -- uncaught, surfacing as an HTTP 500 from
    /api/investments/risk/optimize and taking the whole Investments page
    down. It's reachable from the UI with no trickery at all: the floor and
    cap sliders each span 0-100 independently, with no cross-validation.
    """
    created = client.post(
        "/api/investments/sector-constraints",
        json={"sector": "technology", "floor_pct": 5.0, "cap_pct": 30.0},
        headers=auth_headers,
    )
    assert created.status_code == 200
    bad_payload = {"sector": "technology", "floor_pct": 40.0, "cap_pct": 2.0}

    if method == "post":
        response = client.post("/api/investments/sector-constraints", json=bad_payload, headers=auth_headers)
    else:
        response = client.put(
            f"/api/investments/sector-constraints/{created.json()['id']}", json=bad_payload, headers=auth_headers,
        )

    assert response.status_code == 422

    # The rejected write must not have taken effect -- the stored row keeps
    # its original, valid floor/cap.
    listed = client.get("/api/investments/sector-constraints", headers=auth_headers)
    assert [(c["floor_pct"], c["cap_pct"]) for c in listed.json()] == [(5.0, 30.0)]


@pytest.mark.parametrize("method", ["post", "put"])
def test_ticker_constraint_rejects_floor_above_cap(client, auth_headers, method):
    """Ticker mirror of test_sector_constraint_rejects_floor_above_cap --
    both payloads share the same _validate_floor_cap check, and both feed the
    same scipy `bounds` argument."""
    created = client.post(
        "/api/investments/ticker-constraints",
        json={"ticker": "VOO", "floor_pct": 5.0, "cap_pct": 30.0},
        headers=auth_headers,
    )
    assert created.status_code == 200
    bad_payload = {"ticker": "VOO", "floor_pct": 40.0, "cap_pct": 2.0}

    if method == "post":
        response = client.post("/api/investments/ticker-constraints", json=bad_payload, headers=auth_headers)
    else:
        response = client.put(
            f"/api/investments/ticker-constraints/{created.json()['id']}", json=bad_payload, headers=auth_headers,
        )

    assert response.status_code == 422

    listed = client.get("/api/investments/ticker-constraints", headers=auth_headers)
    assert [(c["floor_pct"], c["cap_pct"]) for c in listed.json()] == [(5.0, 30.0)]


@pytest.mark.parametrize(
    "floor_pct,cap_pct",
    [(-5.0, 30.0), (5.0, 130.0)],
    ids=["negative_floor", "cap_above_100"],
)
def test_constraints_reject_out_of_range_percentages(client, auth_headers, floor_pct, cap_pct):
    """The other half of the 0 <= floor <= cap <= 100 invariant. A negative
    floor or a >100% cap is meaningless as a portfolio weight bound and,
    unlike floor > cap, would be silently accepted by the solver rather than
    raising -- producing a nonsense allocation instead of an error."""
    sector = client.post(
        "/api/investments/sector-constraints",
        json={"sector": "energy", "floor_pct": floor_pct, "cap_pct": cap_pct},
        headers=auth_headers,
    )
    assert sector.status_code == 422

    ticker = client.post(
        "/api/investments/ticker-constraints",
        json={"ticker": "VTI", "floor_pct": floor_pct, "cap_pct": cap_pct},
        headers=auth_headers,
    )
    assert ticker.status_code == 422


def test_sector_constraint_list_still_readable_with_preexisting_inverted_row(client, db_session, auth_headers):
    """A row that predates the floor/cap validator (or was written straight
    to the DB) must stay READABLE -- otherwise the new validation would lock
    the user out of the very row they need to see in order to fix it.

    This pins the reason SectorConstraintResponse no longer inherits
    SectorConstraintPayload: FastAPI validates `response_model` on the way
    out too, so an inherited validator would turn this GET into a 500.
    """
    from app.models import SectorConstraint

    db_session.add(SectorConstraint(user_id=1, sector="materials", floor_pct=40.0, cap_pct=2.0))
    db_session.commit()

    listed = client.get("/api/investments/sector-constraints", headers=auth_headers)
    assert listed.status_code == 200
    row = next(c for c in listed.json() if c["sector"] == "materials")
    assert (row["floor_pct"], row["cap_pct"]) == (40.0, 2.0)

    # ...and a corrective PUT over it is accepted.
    fixed = client.put(
        f"/api/investments/sector-constraints/{row['id']}",
        json={"sector": "materials", "floor_pct": 2.0, "cap_pct": 40.0},
        headers=auth_headers,
    )
    assert fixed.status_code == 200


def test_sector_constraint_missing_id_returns_404(client, auth_headers):
    updated = client.put(
        "/api/investments/sector-constraints/9999",
        json={"sector": "healthcare", "floor_pct": 1.0, "cap_pct": 2.0},
        headers=auth_headers,
    )
    assert updated.status_code == 404

    deleted = client.delete("/api/investments/sector-constraints/9999", headers=auth_headers)
    assert deleted.status_code == 404


# ─── Ticker constraints ─────────────────────────────────────────────────────
# Mirrors the sector-constraint tests above exactly, substituting `ticker`
# for `sector` -- since the endpoints themselves are a direct mirror.

def test_ticker_constraint_crud(client, auth_headers):
    create = client.post(
        "/api/investments/ticker-constraints",
        json={"ticker": "VOO", "floor_pct": 5.0, "cap_pct": 100.0},
        headers=auth_headers,
    )
    assert create.status_code == 200
    body = create.json()
    assert body["ticker"] == "VOO"
    assert body["floor_pct"] == 5.0
    assert body["cap_pct"] == 100.0
    constraint_id = body["id"]

    listed = client.get("/api/investments/ticker-constraints", headers=auth_headers)
    assert listed.status_code == 200
    assert any(c["id"] == constraint_id for c in listed.json())

    # `ticker` is required by TickerConstraintPayload even on PUT, mirroring
    # SectorConstraintPayload's same requirement -- see the comment in
    # test_sector_constraint_crud above.
    updated = client.put(
        f"/api/investments/ticker-constraints/{constraint_id}",
        json={"ticker": "VOO", "floor_pct": 8.0, "cap_pct": 90.0},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["floor_pct"] == 8.0
    assert updated_body["cap_pct"] == 90.0

    # Verify the update was actually persisted, not just echoed in the PUT response.
    listed_after_update = client.get("/api/investments/ticker-constraints", headers=auth_headers)
    matched = next(c for c in listed_after_update.json() if c["id"] == constraint_id)
    assert matched["floor_pct"] == 8.0

    deleted = client.delete(f"/api/investments/ticker-constraints/{constraint_id}", headers=auth_headers)
    assert deleted.status_code == 200
    listed_after = client.get("/api/investments/ticker-constraints", headers=auth_headers)
    assert not any(c["id"] == constraint_id for c in listed_after.json())


def test_ticker_constraint_duplicate_ticker_returns_409(client, auth_headers):
    client.post(
        "/api/investments/ticker-constraints",
        json={"ticker": "VOO", "floor_pct": 0.0, "cap_pct": 100.0},
        headers=auth_headers,
    )
    dup = client.post(
        "/api/investments/ticker-constraints",
        json={"ticker": "VOO", "floor_pct": 0.0, "cap_pct": 100.0},
        headers=auth_headers,
    )
    assert dup.status_code == 409


def test_ticker_constraint_missing_id_returns_404(client, auth_headers):
    updated = client.put(
        "/api/investments/ticker-constraints/9999",
        json={"ticker": "VOO", "floor_pct": 1.0, "cap_pct": 2.0},
        headers=auth_headers,
    )
    assert updated.status_code == 404

    deleted = client.delete("/api/investments/ticker-constraints/9999", headers=auth_headers)
    assert deleted.status_code == 404
