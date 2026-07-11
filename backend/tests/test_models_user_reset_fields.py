"""New User columns for email-based password reset."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Base, User  # noqa: E402


def test_user_has_reset_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    expires = datetime.utcnow() + timedelta(hours=1)
    s.add(User(
        id=1, username="default_user",
        email="me@example.com",
        reset_code_hash="scrypt$1$1$1$aa$bb",
        reset_code_expires_at=expires,
    ))
    s.commit()
    s.close()

    s2 = Session()
    user = s2.query(User).filter(User.id == 1).first()
    assert user.email == "me@example.com"
    assert user.reset_code_hash == "scrypt$1$1$1$aa$bb"
    assert user.reset_code_expires_at == expires
    s2.close()


def test_reset_fields_default_to_none(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(User(id=1, username="default_user"))
    s.commit()
    user = s.query(User).filter(User.id == 1).first()
    assert user.email is None
    assert user.reset_code_hash is None
    assert user.reset_code_expires_at is None
    s.close()
