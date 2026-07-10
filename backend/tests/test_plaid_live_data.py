"""Tests for Plaid update mode, sync error reporting, and error parsing."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, create_autospec, patch

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PLAID_CLIENT_ID", "test_client_id")
os.environ.setdefault("PLAID_SANDBOX_SECRET", "test_sandbox_secret")

import pytest  # noqa: E402
import requests  # noqa: E402

from app.plaid_errors import extract_plaid_error, is_login_required  # noqa: E402
from app.plaid_service import PlaidService  # noqa: E402


def test_extract_plaid_error_from_response():
    response = create_autospec(requests.Response, instance=True)
    response.json.return_value = {
        "error_code": "ITEM_LOGIN_REQUIRED",
        "error_message": "the login details of this item have changed",
    }
    response.text = "error"
    code, msg = extract_plaid_error(response)
    assert code == "ITEM_LOGIN_REQUIRED"
    assert "login details" in msg


def test_extract_plaid_error_from_value_error_string():
    code, msg = extract_plaid_error(
        ValueError("Failed to sync transactions: ITEM_LOGIN_REQUIRED — please update")
    )
    assert code == "ITEM_LOGIN_REQUIRED"


def test_is_login_required():
    assert is_login_required("ITEM_LOGIN_REQUIRED")
    assert not is_login_required("PRODUCT_NOT_READY")
    assert not is_login_required(None)


@patch("app.plaid_service.requests.post")
def test_create_link_token_update_mode_includes_access_token(mock_post):
    mock_post.return_value = MagicMock(
        ok=True,
        json=lambda: {"link_token": "link-sandbox-test"},
    )
    token, oauth = PlaidService.create_link_token(1, access_token="access-sandbox-test")
    assert token == "link-sandbox-test"
    assert oauth is False
    payload = mock_post.call_args.kwargs["json"]
    assert payload["access_token"] == "access-sandbox-test"


@patch("app.plaid_service.requests.post")
def test_create_link_token_new_link_omits_access_token(mock_post):
    mock_post.return_value = MagicMock(
        ok=True,
        json=lambda: {"link_token": "link-sandbox-new"},
    )
    token, oauth = PlaidService.create_link_token(1)
    assert token == "link-sandbox-new"
    assert oauth is False
    payload = mock_post.call_args.kwargs["json"]
    assert "access_token" not in payload


@patch("app.plaid_service.requests.post")
def test_create_link_token_retries_without_unregistered_redirect(mock_post, monkeypatch):
    monkeypatch.setenv("PLAID_ENV", "production")
    first = create_autospec(requests.Response, instance=True)
    first.ok = False
    first.json.return_value = {
        "error_code": "INVALID_FIELD",
        "error_message": "OAuth redirect URI must be configured in the developer dashboard.",
    }
    first.text = "error"
    second = MagicMock(ok=True, json=lambda: {"link_token": "link-no-oauth"})
    mock_post.side_effect = [first, second]

    token, oauth = PlaidService.create_link_token(
        1,
        redirect_uri="https://example.ngrok-free.app/",
    )
    assert token == "link-no-oauth"
    assert oauth is False
    assert mock_post.call_count == 2
    assert "redirect_uri" not in mock_post.call_args_list[1].kwargs["json"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("BUDGETS_DATABASE_URL", f"sqlite:///{tmp_path / 'budgets.db'}")

    import importlib
    from app import database
    importlib.reload(database)
    from app.models import Base
    Base.metadata.create_all(bind=database.engine)
    database.init_db()

    import main
    importlib.reload(main)
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _auth_headers(client):
    r = client.post("/api/auth/register", json={"username": "tester", "password": "password1234"})
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@patch("app.routes.plaid.PlaidService.exchange_public_token")
@patch("app.routes.plaid.PlaidService.get_accounts_with_institution")
def test_set_access_token_updates_existing_item(mock_accounts, mock_exchange, client):
    headers = _auth_headers(client)
    mock_exchange.return_value = ("new-access", "item_plaid_abc")
    mock_accounts.return_value = ([{
        "plaid_account_id": "acc_1",
        "name": "Checking",
        "type": "depository",
        "subtype": "checking",
        "current_balance": 100.0,
    }], {
        "institution_id": "ins_test",
        "name": "Test Bank",
        "logo": None,
        "primary_color": None,
    })

    first = client.post(
        "/api/plaid/set_access_token",
        json={"public_token": "pub_1"},
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["updated"] is False

    second = client.post(
        "/api/plaid/set_access_token",
        json={"public_token": "pub_2"},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["updated"] is True


@patch("app.routes.plaid.sync_item")
def test_sync_reports_per_item_failures(mock_sync_item, client):
    headers = _auth_headers(client)

    from app.database import SessionLocal
    from app.models import Item, User
    from app.security import encrypt_token

    db = SessionLocal()
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, username="default_user", password_hash="x")
        db.add(user)
    item = Item(
        user_id=1,
        item_id="item_fail_test",
        institution_name="Fail Bank",
        access_token_encrypted=encrypt_token("tok"),
    )
    db.add(item)
    db.commit()
    db.close()

    mock_sync_item.side_effect = ValueError("Failed to sync: ITEM_LOGIN_REQUIRED — update credentials")

    r = client.post("/api/plaid/sync", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["failed_count"] == 1
    assert data["success"] is False
    assert data["items"][0]["status"] == "login_required"
    assert "ITEM_LOGIN_REQUIRED" in (data["items"][0]["error"] or "")


@patch("app.routes.plaid.decrypt_token")
@patch("app.routes.plaid.PlaidService.create_link_token")
def test_create_link_token_update_mode_route(mock_create, mock_decrypt, client):
    headers = _auth_headers(client)
    mock_decrypt.return_value = "decrypted-access"

    from app.database import SessionLocal
    from app.models import Item
    from app.security import encrypt_token

    db = SessionLocal()
    item = Item(
        user_id=1,
        item_id="item_update_test",
        institution_name="Update Bank",
        access_token_encrypted=encrypt_token("tok"),
    )
    db.add(item)
    db.commit()
    item_id = item.id
    db.close()

    mock_create.return_value = ("link-update-token", True)

    r = client.post(
        "/api/plaid/create_link_token",
        json={"item_id": item_id},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["link_token"] == "link-update-token"
    assert data["update_mode"] is True
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["access_token"] == "decrypted-access"
