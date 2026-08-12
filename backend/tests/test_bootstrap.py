from __future__ import annotations

import json
import os
from importlib import reload

import pytest


def _fresh(monkeypatch, tmp_path, *, desktop=False, use_appdata=False):
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path))
    if desktop:
        monkeypatch.setenv("LEDGER_DESKTOP", "1")
    else:
        monkeypatch.delenv("LEDGER_DESKTOP", raising=False)
    if use_appdata:
        monkeypatch.setenv("LEDGER_USE_APPDATA", "1")
    else:
        monkeypatch.delenv("LEDGER_USE_APPDATA", raising=False)
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BUDGETS_DATABASE_URL", raising=False)
    from app import paths, bootstrap

    reload(paths)
    reload(bootstrap)
    return bootstrap


def test_noop_when_not_desktop(monkeypatch, tmp_path):
    b = _fresh(monkeypatch, tmp_path)
    b.bootstrap_desktop()
    assert "ENCRYPTION_KEY" not in os.environ
    assert not (tmp_path / "config.json").exists()


def test_generates_key_and_sets_env(monkeypatch, tmp_path):
    b = _fresh(monkeypatch, tmp_path, desktop=True)
    b.bootstrap_desktop()
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["ENCRYPTION_KEY"]
    assert os.environ["ENCRYPTION_KEY"] == cfg["ENCRYPTION_KEY"]
    assert os.environ["DATABASE_URL"] == f"sqlite:///{tmp_path / 'ledger.db'}"
    assert os.environ["BUDGETS_DATABASE_URL"] == f"sqlite:///{tmp_path / 'budgets.db'}"
    if os.name == "posix":
        assert (os.stat(tmp_path / "config.json").st_mode & 0o777) == 0o600


def test_reuses_existing_key(monkeypatch, tmp_path):
    b = _fresh(monkeypatch, tmp_path, desktop=True)
    b.bootstrap_desktop()
    first = os.environ["ENCRYPTION_KEY"]
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    b.bootstrap_desktop()
    assert os.environ["ENCRYPTION_KEY"] == first


def test_does_not_overwrite_preset_env(monkeypatch, tmp_path):
    b = _fresh(monkeypatch, tmp_path, desktop=True)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom.db")
    b.bootstrap_desktop()
    assert os.environ["DATABASE_URL"] == "sqlite:///custom.db"


def test_refuses_new_key_when_db_exists(monkeypatch, tmp_path):
    (tmp_path / "ledger.db").write_bytes(b"not empty")
    b = _fresh(monkeypatch, tmp_path, desktop=True)
    with pytest.raises(RuntimeError):
        b.bootstrap_desktop()


def test_use_appdata_loads_existing_key(monkeypatch, tmp_path):
    key = "test-key-not-a-real-fernet-value"
    (tmp_path / "config.json").write_text(json.dumps({"ENCRYPTION_KEY": key}))
    (tmp_path / "ledger.db").write_bytes(b"x")
    b = _fresh(monkeypatch, tmp_path, use_appdata=True)
    b.bootstrap_desktop()
    assert os.environ["ENCRYPTION_KEY"] == key
    assert os.environ["DATABASE_URL"] == f"sqlite:///{tmp_path / 'ledger.db'}"
    assert os.environ["BUDGETS_DATABASE_URL"] == f"sqlite:///{tmp_path / 'budgets.db'}"
    # Must not flip desktop mode — health.desktop stays driven by LEDGER_DESKTOP.
    assert not b._desktop_enabled()
    assert b._use_appdata_enabled()


def test_use_appdata_refuses_without_config(monkeypatch, tmp_path):
    b = _fresh(monkeypatch, tmp_path, use_appdata=True)
    with pytest.raises(RuntimeError, match="LEDGER_USE_APPDATA"):
        b.bootstrap_desktop()
    assert not (tmp_path / "config.json").exists()
