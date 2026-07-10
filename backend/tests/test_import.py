from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from cryptography.fernet import Fernet

# A known key we will "import from" the source install.
SRC_KEY = Fernet.generate_key().decode()
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402


def _make_source(dirpath: Path, key: str, with_item: bool = True):
    dirpath.mkdir(parents=True, exist_ok=True)
    # minimal ledger.db with an items table + one encrypted token
    con = sqlite3.connect(dirpath / "ledger.db")
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, access_token_encrypted TEXT)")
    if with_item:
        token = Fernet(key.encode()).encrypt(b"access-sandbox-123").decode()
        con.execute("INSERT INTO items (access_token_encrypted) VALUES (?)", (token,))
    con.commit()
    con.close()
    (dirpath / "budgets.db").write_bytes(b"")
    (dirpath / ".env").write_text(
        f"ENCRYPTION_KEY={key}\nPLAID_CLIENT_ID=cid\nPLAID_SANDBOX_SECRET=sec\nPLAID_ENV=sandbox\n"
    )


def test_import_happy_path(tmp_path, monkeypatch):
    src = tmp_path / "src" / "backend"
    _make_source(src, SRC_KEY)
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("LEDGER_APPDATA", str(appdata))

    from importlib import reload
    from app import paths
    reload(paths)
    from app.routes import settings as settings_mod

    result = settings_mod._do_import(str(src), confirm_overwrite=False)
    assert result["imported_items"] == 1
    assert result["restart_required"] is True
    assert (appdata / "ledger.db").exists()
    import json
    cfg = json.loads((appdata / "config.json").read_text())
    assert cfg["ENCRYPTION_KEY"] == SRC_KEY


def test_import_wrong_key_rejected(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _make_source(src, SRC_KEY)
    # Corrupt the .env key so decrypt fails
    (src / ".env").write_text(f"ENCRYPTION_KEY={Fernet.generate_key().decode()}\n")
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path / "appdata"))
    from importlib import reload
    from app import paths
    reload(paths)
    from app.routes import settings as settings_mod
    with pytest.raises(Exception):
        settings_mod._do_import(str(src), confirm_overwrite=False)


def test_import_symlink_escape_rejected(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    outside = tmp_path / "outside.db"
    outside.write_bytes(b"secret")
    os.symlink(outside, src / "ledger.db")
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path / "appdata"))
    from importlib import reload
    from app import paths
    reload(paths)
    from app.routes import settings as settings_mod
    with pytest.raises(Exception):
        settings_mod._do_import(str(src), confirm_overwrite=False)


def _make_populated_target(appdata: Path):
    """Pre-populate the app-data ledger.db with a marker `items` row."""
    appdata.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(appdata / "ledger.db")
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, access_token_encrypted TEXT)")
    con.execute("INSERT INTO items (access_token_encrypted) VALUES ('marker-token')")
    con.commit()
    con.close()


def test_import_backs_up_existing_target(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _make_source(src, SRC_KEY)
    appdata = tmp_path / "appdata"
    _make_populated_target(appdata)
    monkeypatch.setenv("LEDGER_APPDATA", str(appdata))

    from importlib import reload
    from app import paths
    reload(paths)
    from app.routes import settings as settings_mod

    settings_mod._do_import(str(src), confirm_overwrite=True)

    backups = list(appdata.glob("ledger.db.bak-*"))
    assert len(backups) >= 1


def test_import_refuses_populated_target_without_confirm(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _make_source(src, SRC_KEY)
    appdata = tmp_path / "appdata"
    _make_populated_target(appdata)
    monkeypatch.setenv("LEDGER_APPDATA", str(appdata))

    from importlib import reload
    from app import paths
    reload(paths)
    from app.routes import settings as settings_mod
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        settings_mod._do_import(str(src), confirm_overwrite=False)
    assert exc_info.value.status_code == 409

    # Target must not have been overwritten.
    con = sqlite3.connect(appdata / "ledger.db")
    try:
        row = con.execute("SELECT access_token_encrypted FROM items").fetchone()
    finally:
        con.close()
    assert row[0] == "marker-token"


def test_import_migrates_decryptable_secret(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _make_source(src, SRC_KEY)
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("LEDGER_APPDATA", str(appdata))

    from importlib import reload
    from app import paths
    reload(paths)
    from app.routes import settings as settings_mod

    settings_mod._do_import(str(src), confirm_overwrite=False)

    con = sqlite3.connect(appdata / "ledger.db")
    try:
        secret_row = con.execute("SELECT value FROM app_config WHERE key = 'PLAID_SECRET'").fetchone()
        cid_row = con.execute("SELECT value FROM app_config WHERE key = 'PLAID_CLIENT_ID'").fetchone()
    finally:
        con.close()
    assert Fernet(SRC_KEY.encode()).decrypt(secret_row[0].encode()).decode() == "sec"
    assert cid_row[0] == "cid"


def test_import_allows_empty_items_source(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _make_source(src, SRC_KEY, with_item=False)
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("LEDGER_APPDATA", str(appdata))

    from importlib import reload
    from app import paths
    reload(paths)
    from app.routes import settings as settings_mod

    result = settings_mod._do_import(str(src), confirm_overwrite=False)
    assert result["imported_items"] == 0
    import json
    cfg = json.loads((appdata / "config.json").read_text())
    assert cfg["ENCRYPTION_KEY"] == SRC_KEY
