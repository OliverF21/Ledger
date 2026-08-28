from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest


@pytest.fixture(autouse=True)
def _isolated_key_store():
    """Never touch the real OS keychain during tests."""
    from app import key_store

    key_store.use_memory_backend()
    yield
    key_store.use_memory_backend()
