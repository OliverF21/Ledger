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


def test_persist_keeps_file_when_not_safe_to_strip(tmp_path, monkeypatch):
    """If the keychain cannot be made update-stable, keep the file recovery copy."""
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path))
    from importlib import reload
    from app import paths, key_store

    reload(paths)
    key_store.use_memory_backend()
    monkeypatch.setattr(key_store, "_safe_to_drop_file_copy", lambda: False)
    key_store.persist("secret-key")
    assert key_store.get_os_key() == "secret-key"
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["ENCRYPTION_KEY"] == "secret-key"


def test_load_prefers_file_when_keychain_differs(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path))
    from importlib import reload
    from app import paths, key_store

    reload(paths)
    key_store.use_memory_backend()
    key_store.set_os_key("from-keychain")
    key_store.write_file_key("from-file")
    assert key_store.load() == "from-file"
    assert key_store.get_os_key() == "from-file"


def test_set_os_key_requires_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path))
    from importlib import reload
    from app import paths, key_store

    reload(paths)
    key_store._use_memory = False
    key_store._backend_ready = True
    monkeypatch.setattr(key_store, "_os_set", lambda service, account, password: None)
    monkeypatch.setattr(key_store, "_os_get", lambda service, account: None)
    assert key_store.set_os_key("k") is False
    monkeypatch.setattr(key_store, "_os_get", lambda service, account: "k")
    assert key_store.set_os_key("k") is True


def test_get_os_key_falls_back_to_legacy_account(tmp_path, monkeypatch):
    monkeypatch.delenv("LEDGER_APPDATA", raising=False)
    from app import paths, key_store

    key_store.use_memory_backend()
    monkeypatch.setattr(paths, "app_data_dir", lambda: tmp_path)
    legacy = f"encryption-key:{tmp_path.resolve()}"
    key_store._memory[(key_store.SERVICE, legacy)] = "legacy-key"
    assert key_store._primary_account() == "encryption-key"
    assert key_store.get_os_key() == "legacy-key"


def test_unsigned_mac_drops_file_only_after_open_acl(monkeypatch, tmp_path):
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path))
    from importlib import reload
    from app import paths, key_store

    reload(paths)
    key_store._use_memory = False
    key_store._signed_cache = None
    key_store._last_write_used_open_acl = False
    monkeypatch.setattr(key_store.sys, "platform", "darwin")
    monkeypatch.setattr(key_store, "_macos_has_stable_signature", lambda: False)
    monkeypatch.setattr(key_store, "_darwin_ensure_open_acl", lambda *args, **kwargs: False)
    assert key_store._safe_to_drop_file_copy() is False
    monkeypatch.setattr(key_store, "_darwin_ensure_open_acl", lambda *args, **kwargs: True)
    assert key_store._safe_to_drop_file_copy() is True
    key_store._last_write_used_open_acl = True
    monkeypatch.setattr(key_store, "_darwin_ensure_open_acl", lambda *args, **kwargs: False)
    assert key_store._safe_to_drop_file_copy() is True
