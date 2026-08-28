from __future__ import annotations

import json


def test_persist_does_not_write_plaintext_when_keychain_works(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path))
    from importlib import reload
    from app import paths, key_store

    reload(paths)
    key_store.use_memory_backend()
    key_store.persist("secret-key")
    assert key_store.get_os_key() == "secret-key"
    assert key_store.load() == "secret-key"
    assert not (tmp_path / "config.json").exists()


def test_load_migrates_and_strips_config_json(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path))
    from importlib import reload
    from app import paths, key_store

    reload(paths)
    key_store.use_memory_backend()
    (tmp_path / "config.json").write_text(json.dumps({"ENCRYPTION_KEY": "legacy", "other": "keep"}))
    assert key_store.load() == "legacy"
    assert key_store.get_os_key() == "legacy"
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert "ENCRYPTION_KEY" not in cfg
    assert cfg["other"] == "keep"
