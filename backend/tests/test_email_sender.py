"""email_sender: the emergency (reset-only) Resend key must be fully
independent from the weekly-digest RESEND_API_KEY — env-only, never
app_config, never used to send anything but a reset code."""
from __future__ import annotations

import os

import pytest

from app import email_sender


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("RESET_EMERGENCY_RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)


def test_emergency_key_unset_by_default():
    assert email_sender.get_emergency_resend_api_key() == ""
    assert email_sender.is_reset_email_configured() is False


def test_emergency_key_reads_env_only(monkeypatch):
    monkeypatch.setenv("RESET_EMERGENCY_RESEND_API_KEY", "emergency_secret")
    assert email_sender.get_emergency_resend_api_key() == "emergency_secret"
    assert email_sender.is_reset_email_configured() is True


def test_weekly_key_unaffected_by_emergency_key(monkeypatch):
    monkeypatch.setenv("RESET_EMERGENCY_RESEND_API_KEY", "emergency_secret")
    monkeypatch.setenv("RESEND_API_KEY", "weekly_secret")
    assert email_sender.get_resend_api_key() == "weekly_secret"
    assert email_sender.get_emergency_resend_api_key() == "emergency_secret"


def test_send_password_reset_email_uses_emergency_key(monkeypatch):
    monkeypatch.setenv("RESET_EMERGENCY_RESEND_API_KEY", "emergency_secret")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(email_sender.requests, "post", fake_post)
    ok = email_sender.send_password_reset_email("user@example.com", "Your code", "<p>042917</p>")
    assert ok is True
    assert captured["headers"]["Authorization"] == "Bearer emergency_secret"
    assert captured["json"]["to"] == ["user@example.com"]


def test_send_password_reset_email_noop_when_unconfigured():
    assert email_sender.send_password_reset_email("user@example.com", "Your code", "<p>x</p>") is False


def test_send_password_reset_email_never_uses_weekly_key(monkeypatch):
    """Both keys set to different values: the actual outgoing Authorization
    header must carry the emergency key's value, never the weekly key's."""
    monkeypatch.setenv("RESET_EMERGENCY_RESEND_API_KEY", "emergency_secret")
    monkeypatch.setenv("RESEND_API_KEY", "weekly_secret")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(email_sender.requests, "post", fake_post)
    ok = email_sender.send_password_reset_email("user@example.com", "Your code", "<p>042917</p>")
    assert ok is True
    assert captured["headers"]["Authorization"] == "Bearer emergency_secret"
    assert captured["headers"]["Authorization"] != "Bearer weekly_secret"
