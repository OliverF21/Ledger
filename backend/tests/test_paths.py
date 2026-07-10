from __future__ import annotations

import os
from pathlib import Path


def test_app_data_dir_honors_override(tmp_path, monkeypatch):
    target = tmp_path / "LedgerData"
    monkeypatch.setenv("LEDGER_APPDATA", str(target))
    from importlib import reload
    from app import paths
    reload(paths)

    d = paths.app_data_dir()
    assert d == target
    assert d.is_dir()
    # 0700 on POSIX
    if os.name == "posix":
        assert (d.stat().st_mode & 0o777) == 0o700


def test_path_helpers(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_APPDATA", str(tmp_path))
    from importlib import reload
    from app import paths
    reload(paths)

    assert paths.config_path() == tmp_path / "config.json"
    assert paths.ledger_db_path() == tmp_path / "ledger.db"
    assert paths.budgets_db_path() == tmp_path / "budgets.db"
