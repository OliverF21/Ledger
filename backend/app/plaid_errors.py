"""
Parse Plaid API error payloads from requests HTTPError / ValueError wrappers.
"""

from __future__ import annotations

import json
from typing import Any

import requests

# Plaid error codes that mean the user must re-authenticate via Link update mode.
LOGIN_REQUIRED_CODES = frozenset({
    "ITEM_LOGIN_REQUIRED",
    "INVALID_ACCESS_TOKEN",
    "ITEM_LOCKED",
    "USER_SETUP_REQUIRED",
    "USER_ACCOUNT_REVOKED",
})


def extract_plaid_error(exc: BaseException | requests.Response) -> tuple[str | None, str]:
    """
    Return (error_code, human_message) from a Plaid API failure.
    Accepts a requests Response (not ok) or an exception with a .response attr.
    """
    response: requests.Response | None = None
    if isinstance(exc, requests.Response):
        response = exc
    else:
        response = getattr(exc, "response", None)

    if response is not None:
        try:
            body: dict[str, Any] = response.json()
            code = body.get("error_code")
            message = body.get("error_message") or body.get("display_message") or response.text
            return code, message
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass

    text = str(exc)
    for code in LOGIN_REQUIRED_CODES:
        if code in text:
            return code, text
    return None, text


def raise_for_plaid_response(response: requests.Response, context: str) -> None:
    """Raise ValueError with Plaid error_code embedded when response is not OK."""
    if response.ok:
        return
    code, message = extract_plaid_error(response)
    if code:
        raise ValueError(f"{context}: {code}. {message}")
    response.raise_for_status()


def is_login_required(code: str | None) -> bool:
    return code in LOGIN_REQUIRED_CODES
