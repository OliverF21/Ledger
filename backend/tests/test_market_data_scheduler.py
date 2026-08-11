from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from unittest.mock import MagicMock  # noqa: E402

from app.scheduler import sync_market_data_job  # noqa: E402


def test_sync_market_data_job_calls_price_sync_and_rate_refresh(monkeypatch):
    import app.services.price_sync_service as price_sync_module
    import app.risk_free_rate as rfr_module

    price_sync_mock = MagicMock(return_value={"tickers_synced": 3, "rows_upserted": 10})
    rate_mock = MagicMock(return_value=5.1)
    monkeypatch.setattr(price_sync_module, "sync_market_prices", price_sync_mock)
    monkeypatch.setattr(rfr_module, "fetch_and_cache_risk_free_rate", rate_mock)

    sync_market_data_job()

    price_sync_mock.assert_called_once()
    rate_mock.assert_called_once()


def test_sync_market_data_job_swallows_exceptions(monkeypatch):
    import app.services.price_sync_service as price_sync_module

    def _raise(db):
        raise RuntimeError("boom")

    monkeypatch.setattr(price_sync_module, "sync_market_prices", _raise)

    sync_market_data_job()  # must not raise
