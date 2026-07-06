"""Telegram-алертинг (ML_AUDIT_REPORT.md P0-6, Фаза 1.5).

Контракт send_telegram_alert:
- без TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID → False, без сетевых вызовов;
- HTTP 200 → True; не-200 → False; исключение сети → False (не пробрасывается);
- текст обрезается до лимита Telegram.
"""

import httpx
import pytest

import app.services.alerting as alerting
from app.config import settings


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123:test-token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "-100500")


def test_not_configured_returns_false_without_network(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")

    def boom(*a, **k):
        raise AssertionError("no network calls expected when unconfigured")

    monkeypatch.setattr(alerting.httpx, "post", boom)
    assert alerting.send_telegram_alert("test") is False
    assert alerting.telegram_configured() is False


def test_success_returns_true_and_truncates(configured, monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(alerting.httpx, "post", fake_post)
    assert alerting.send_telegram_alert("x" * 10000) is True
    assert "123:test-token" in captured["url"]
    assert captured["json"]["chat_id"] == "-100500"
    assert len(captured["json"]["text"]) <= 4000


def test_http_error_returns_false(configured, monkeypatch):
    monkeypatch.setattr(
        alerting.httpx, "post",
        lambda url, json, timeout: httpx.Response(
            403, request=httpx.Request("POST", url), text="forbidden"
        ),
    )
    assert alerting.send_telegram_alert("test") is False


def test_network_exception_swallowed(configured, monkeypatch):
    def fake_post(*a, **k):
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(alerting.httpx, "post", fake_post)
    assert alerting.send_telegram_alert("test") is False
