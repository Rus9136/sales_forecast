"""Unit tests for `IikoAuthService` — token fetch, caching, refresh, errors.

Uses respx as a context manager (the `@respx.mock` decorator does not
compose cleanly with pytest-asyncio's auto mode). The auth service caches
the token until 5 minutes before its 60-minute TTL; tests verify both the
freshly-fetched and cached paths.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest
import respx

from app.services.iiko_auth import IikoAuthService

pytestmark = pytest.mark.unit

BASE_URL = "https://test-iiko.example.com"
AUTH_URL = f"{BASE_URL}/resto/api/auth"


@pytest.fixture(autouse=True)
def _set_iiko_creds(monkeypatch):
    """IikoAuthService reads login/password from settings at __init__ time."""
    from app.config import settings

    monkeypatch.setattr(settings, "IIKO_LOGIN", "test-login")
    monkeypatch.setattr(settings, "IIKO_PASSWORD", "test-pass-hash")


class TestRefreshToken:
    async def test_returns_token_text_stripped(self) -> None:
        with respx.mock:
            respx.get(AUTH_URL).mock(
                return_value=httpx.Response(200, text=" abc-token \n")
            )
            svc = IikoAuthService(BASE_URL)

            token = await svc._refresh_token()
            assert token == "abc-token"
            assert svc.token == "abc-token"
            assert svc.token_expires_at is not None
            # ~55 min TTL (refreshed 5 min before iiko's 60 min expiry).
            assert svc.token_expires_at - datetime.now() < timedelta(minutes=56)

    async def test_passes_login_and_password_query_params(self) -> None:
        with respx.mock:
            route = respx.get(AUTH_URL).mock(
                return_value=httpx.Response(200, text="t")
            )
            svc = IikoAuthService(BASE_URL)

            await svc._refresh_token()
            request = route.calls.last.request
            assert request.url.params["login"] == "test-login"
            assert request.url.params["pass"] == "test-pass-hash"

    async def test_401_raises_http_error(self) -> None:
        with respx.mock:
            respx.get(AUTH_URL).mock(
                return_value=httpx.Response(401, text="bad creds")
            )
            svc = IikoAuthService(BASE_URL)
            with pytest.raises(httpx.HTTPError):
                await svc._refresh_token()

    async def test_500_raises_http_error(self) -> None:
        with respx.mock:
            respx.get(AUTH_URL).mock(return_value=httpx.Response(500))
            svc = IikoAuthService(BASE_URL)
            with pytest.raises(httpx.HTTPError):
                await svc._refresh_token()

    async def test_network_error_raises(self) -> None:
        with respx.mock:
            respx.get(AUTH_URL).mock(side_effect=httpx.ConnectError("boom"))
            svc = IikoAuthService(BASE_URL)
            with pytest.raises(Exception):
                await svc._refresh_token()


class TestGetAuthToken:
    async def test_caches_token_until_expiry(self) -> None:
        with respx.mock:
            route = respx.get(AUTH_URL).mock(
                return_value=httpx.Response(200, text="cached-token")
            )
            svc = IikoAuthService(BASE_URL)

            first = await svc.get_auth_token()
            second = await svc.get_auth_token()
            third = await svc.get_auth_token()

            assert first == second == third == "cached-token"
            # Only ONE HTTP call — the rest hit the cache.
            assert route.call_count == 1

    async def test_refreshes_when_token_expired(self) -> None:
        with respx.mock:
            route = respx.get(AUTH_URL).mock(
                side_effect=[
                    httpx.Response(200, text="old-token"),
                    httpx.Response(200, text="new-token"),
                ]
            )
            svc = IikoAuthService(BASE_URL)

            first = await svc.get_auth_token()
            assert first == "old-token"

            # Force expiry without sleeping.
            svc.token_expires_at = datetime.now() - timedelta(seconds=1)

            second = await svc.get_auth_token()
            assert second == "new-token"
            assert route.call_count == 2

    async def test_refreshes_when_no_token_yet(self) -> None:
        with respx.mock:
            route = respx.get(AUTH_URL).mock(
                return_value=httpx.Response(200, text="fresh")
            )
            svc = IikoAuthService(BASE_URL)
            # Both attributes start as None.
            assert svc.token is None
            assert svc.token_expires_at is None

            token = await svc.get_auth_token()
            assert token == "fresh"
            assert route.call_count == 1
