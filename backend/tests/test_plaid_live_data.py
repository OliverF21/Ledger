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
        json=lambda: {"link_token": "link-sandbox-test", "hosted_link_url": "https://hosted.plaid.com/x"},
    )
    token, hosted_url = PlaidService.create_link_token(1, access_token="access-sandbox-test")
    assert token == "link-sandbox-test"
    assert hosted_url == "https://hosted.plaid.com/x"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["access_token"] == "access-sandbox-test"
    # Hosted Link is what removes the need for a client-side OAuth redirect URI.
    assert payload["hosted_link"] == {}
    assert "redirect_uri" not in payload


@patch("app.plaid_service.requests.post")
def test_create_link_token_new_link_omits_access_token(mock_post):
    mock_post.return_value = MagicMock(
        ok=True,
        json=lambda: {"link_token": "link-sandbox-new", "hosted_link_url": "https://hosted.plaid.com/y"},
    )
    token, hosted_url = PlaidService.create_link_token(1)
    assert token == "link-sandbox-new"
    assert hosted_url == "https://hosted.plaid.com/y"
    payload = mock_post.call_args.kwargs["json"]
    assert "access_token" not in payload
    assert payload["hosted_link"] == {}


@patch("app.plaid_service.requests.post")
def test_get_link_session_pending(mock_post):
    """No completed session yet -> raw response passed through for the route to parse."""
    mock_post.return_value = MagicMock(ok=True, json=lambda: {"link_sessions": []})
    session = PlaidService.get_link_session("link-token-abc")
    assert session == {"link_sessions": []}
    payload = mock_post.call_args.kwargs["json"]
    assert payload["link_token"] == "link-token-abc"


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

    mock_create.return_value = ("link-update-token", "https://hosted.plaid.com/update")

    r = client.post(
        "/api/plaid/create_link_token",
        json={"item_id": item_id},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["link_token"] == "link-update-token"
    assert data["hosted_link_url"] == "https://hosted.plaid.com/update"
    assert data["update_mode"] is True
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["access_token"] == "decrypted-access"


@patch("app.routes.plaid.PlaidService.get_link_session")
def test_link_session_pending(mock_session, client):
    headers = _auth_headers(client)
    mock_session.return_value = {"link_sessions": [{"link_session_id": "s1"}]}
    r = client.get("/api/plaid/link_session?link_token=lt-1", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


@patch("app.routes.plaid.PlaidService.get_link_session")
def test_link_session_error_on_exit(mock_session, client):
    headers = _auth_headers(client)
    mock_session.return_value = {
        "link_sessions": [
            {"on_exit": {"error": {"error_message": "user bailed"}}}
        ]
    }
    r = client.get("/api/plaid/link_session?link_token=lt-2", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert body["message"] == "user bailed"


@patch("app.routes.plaid.PlaidService.get_accounts_with_institution")
@patch("app.routes.plaid.PlaidService.exchange_public_token")
@patch("app.routes.plaid.PlaidService.get_link_session")
def test_link_session_complete_exchanges_and_creates_item(
    mock_session, mock_exchange, mock_accounts, client
):
    headers = _auth_headers(client)
    mock_session.return_value = {
        "link_sessions": [
            {"results": {"item_add_results": [{"public_token": "pub-hosted-1"}]}}
        ]
    }
    mock_exchange.return_value = ("acc-token", "item_plaid_hosted")
    mock_accounts.return_value = ([{
        "plaid_account_id": "acc_h1",
        "name": "Checking",
        "type": "depository",
        "subtype": "checking",
        "current_balance": 42.0,
    }], {
        "institution_id": "ins_h",
        "name": "Hosted Bank",
        "logo": None,
        "primary_color": None,
    })

    r = client.get("/api/plaid/link_session?link_token=lt-3", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "complete"
    assert body["item_id"] == "item_plaid_hosted"
    assert body["updated"] is False
    mock_exchange.assert_called_once_with("pub-hosted-1")
