from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Base  # noqa: E402
from app import app_config  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_plaintext_round_trip(db):
    app_config.set(db, "PLAID_CLIENT_ID", "abc123")
    assert app_config.get(db, "PLAID_CLIENT_ID") == "abc123"


def test_secret_is_encrypted_at_rest(db):
    app_config.set(db, "PLAID_SECRET", "supersecret", secret=True)
    from app.models import AppConfig
    row = db.query(AppConfig).filter_by(key="PLAID_SECRET").one()
    assert row.value != "supersecret"        # stored ciphertext
    assert row.is_secret is True
    assert app_config.get(db, "PLAID_SECRET") == "supersecret"  # decrypts on read


def test_overwrite_and_delete(db):
    app_config.set(db, "PLAID_ENV", "sandbox")
    app_config.set(db, "PLAID_ENV", "production")
    assert app_config.get(db, "PLAID_ENV") == "production"
    app_config.delete(db, "PLAID_ENV")
    assert app_config.get(db, "PLAID_ENV") is None


def test_get_plaid_config_shape(db):
    app_config.set(db, "PLAID_CLIENT_ID", "cid")
    app_config.set(db, "PLAID_SECRET", "sec", secret=True)
    app_config.set(db, "PLAID_ENV", "sandbox")
    cfg = app_config.get_plaid_config(db)
    assert cfg == {"client_id": "cid", "secret": "sec", "env": "sandbox", "redirect_uri": None}
