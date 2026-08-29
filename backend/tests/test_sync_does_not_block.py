"""Boot APIs must stay responsive while a Plaid sync is in flight.

POST /api/plaid/sync talks to Plaid with blocking `requests`. If that work
runs on the asyncio event loop, /api/auth/me and /api/setup/status hang and
the frontend sits on the loading screen until Plaid returns (or forever).
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from types import SimpleNamespace

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PLAID_CLIENT_ID", "test_client_id")
os.environ.setdefault("PLAID_SANDBOX_SECRET", "test_sandbox_secret")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.plaid_service import PlaidService  # noqa: E402


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("BUDGETS_DATABASE_URL", f"sqlite:///{tmp_path / 'budgets.db'}")

    import importlib
    from app import database

    importlib.reload(database)
    from app.models import Base

    Base.metadata.create_all(bind=database.engine)

    import main

    importlib.reload(main)
    from app.auth import require_auth

    main.app.dependency_overrides[require_auth] = lambda: 1
    yield main.app
    main.app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_setup_status_responds_while_sync_is_blocked(app, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocking_sync(_db, _item):
        started.set()
        assert release.wait(timeout=5)
        return {"synced": 0, "removed": 0, "enrichment_backfilled": 0}

    monkeypatch.setattr(
        "app.routes.plaid.get_real_items",
        lambda _db: [SimpleNamespace(id=1, institution_name="Test Bank")],
    )
    monkeypatch.setattr("app.routes.plaid.sync_item", blocking_sync)
    monkeypatch.setattr(PlaidService, "is_configured", staticmethod(lambda: True))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sync_task = asyncio.create_task(client.post("/api/plaid/sync"))
        assert await asyncio.to_thread(started.wait, 2)

        t0 = time.perf_counter()
        status = await client.get("/api/setup/status")
        elapsed = time.perf_counter() - t0

        release.set()
        sync = await sync_task

    assert status.status_code == 200, status.text
    assert elapsed < 0.75, f"setup/status blocked for {elapsed:.2f}s during sync"
    assert sync.status_code == 200, sync.text


def test_plaid_http_calls_set_a_timeout(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["timeout"] = timeout
        raise RuntimeError("stop")

    monkeypatch.setattr("app.plaid_service.requests.post", fake_post)
    with pytest.raises(ValueError):
        PlaidService.sync_transactions("access-token")
    assert captured["timeout"] == PlaidService._HTTP_TIMEOUT_SECONDS
