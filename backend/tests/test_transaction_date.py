"""PUT /api/transactions/{id}/date updates the stored transaction date."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Account, Base, Item, Transaction, User  # noqa: E402


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
        session = memdb()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[database.get_db] = _get_db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture()
def db_session(memdb):
    session = memdb()
    try:
        yield session
    finally:
        session.close()


def _seed_transaction(session, *, removed=False, when=date(2024, 1, 15)) -> int:
    user = User(id=1, username="default_user")
    item = Item(user=user, item_id="item_date", access_token_encrypted="x")
    account = Account(
        item=item,
        plaid_account_id="acct_checking",
        name="Checking",
        type="depository",
    )
    txn = Transaction(
        account=account,
        merchant="Cafe",
        amount=Decimal("12.50"),
        date=when,
        category_user="Dining",
        pending=False,
        removed=removed,
        hidden=False,
    )
    session.add(txn)
    session.commit()
    return txn.id


def test_update_transaction_date(client, db_session):
    txn_id = _seed_transaction(db_session)

    response = client.put(
        f"/api/transactions/{txn_id}/date",
        json={"date": "2024-03-02"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "date": "2024-03-02"}

    row = db_session.query(Transaction).filter(Transaction.id == txn_id).one()
    db_session.refresh(row)
    assert row.date == date(2024, 3, 2)
    assert row.merchant == "Cafe"
    assert row.category_user == "Dining"
    assert row.amount == Decimal("12.50")


def test_update_transaction_date_missing_and_removed(client, db_session):
    removed_id = _seed_transaction(db_session, removed=True)
    headers = {"Authorization": "Bearer test-token"}

    missing = client.put(
        "/api/transactions/99999/date",
        json={"date": "2024-03-02"},
        headers=headers,
    )
    assert missing.status_code == 404

    removed = client.put(
        f"/api/transactions/{removed_id}/date",
        json={"date": "2024-03-02"},
        headers=headers,
    )
    assert removed.status_code == 404

    row = db_session.query(Transaction).filter(Transaction.id == removed_id).one()
    db_session.refresh(row)
    assert row.date == date(2024, 1, 15)


def test_update_transaction_date_rejects_invalid_value(client, db_session):
    txn_id = _seed_transaction(db_session)

    response = client.put(
        f"/api/transactions/{txn_id}/date",
        json={"date": "not-a-date"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 422
    row = db_session.query(Transaction).filter(Transaction.id == txn_id).one()
    db_session.refresh(row)
    assert row.date == date(2024, 1, 15)
