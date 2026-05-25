"""Unit tests for the `iiko_source_domain` tagging in IikoDepartmentLoaderService.

Covers:
- `_domain_host` helper: extracts bare hostname so the stored value is stable
  across `https://x/…` / `http://x:8080/y` / plain `x` inputs.
- `fetch_departments_from_single_domain`: tags every returned dict with the
  bare hostname of the source URL.
- The raw XML parser does NOT inject the field (it's added by the fetch wrapper).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.services.iiko_department_loader import (
    IikoDepartmentLoaderService,
    _domain_host,
)

pytestmark = pytest.mark.unit

DOMAIN = "https://sandy-co-co.iiko.it"


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "IIKO_LOGIN", "x")
    monkeypatch.setattr(settings, "IIKO_PASSWORD", "y")
    monkeypatch.setattr(settings, "IIKO_DOMAINS", DOMAIN)


@pytest.fixture
def loader():
    return IikoDepartmentLoaderService(db=None)  # type: ignore[arg-type]


class TestDomainHost:
    def test_extracts_hostname_from_https_url(self) -> None:
        assert _domain_host("https://sandy-co-co.iiko.it") == "sandy-co-co.iiko.it"

    def test_extracts_hostname_from_http_url(self) -> None:
        assert _domain_host("http://example.com/path/") == "example.com"

    def test_extracts_hostname_from_url_with_port(self) -> None:
        # urlparse drops the port from .hostname (it's available via .port)
        assert _domain_host("http://example.com:8080/x") == "example.com"

    def test_handles_bare_hostname_input(self) -> None:
        # If someone configures IIKO_DOMAINS without a scheme, we still extract.
        assert _domain_host("example.com") == "example.com"

    def test_hostname_lowercases(self) -> None:
        # urlparse normalises host case — store consistently lowercase.
        assert _domain_host("https://EXAMPLE.com") == "example.com"


class TestParserDoesNotInjectSourceDomain:
    """The XML parser is shared across domains. The `iiko_source_domain` field
    is added by `fetch_departments_from_single_domain`, NOT by the parser.
    Guards against future refactors that might accidentally couple them.
    """

    def test_parsed_dict_has_no_source_domain_key(self, loader) -> None:
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>x</id>
                <name>X</name>
                <type>DEPARTMENT</type>
            </corporateItemDto>
        </departments>"""
        d = loader._parse_departments_xml(xml)[0]
        assert "iiko_source_domain" not in d


class TestFetchTagsDictsWithSourceDomain:
    """End-to-end (mocked-network) check that the fetch wrapper attaches the
    hostname to every dict it returns."""

    def test_each_department_tagged_with_source_host(self, loader) -> None:
        xml_body = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>d1</id><name>A</name><type>DEPARTMENT</type>
            </corporateItemDto>
            <corporateItemDto>
                <id>d2</id><name>B</name><type>JURPERSON</type>
            </corporateItemDto>
        </departments>"""

        async def _run() -> list[dict]:
            with respx.mock() as router:
                router.get(f"{DOMAIN}/resto/api/auth").mock(
                    return_value=httpx.Response(200, text="fake-token")
                )
                router.get(f"{DOMAIN}/resto/api/corporation/departments").mock(
                    return_value=httpx.Response(200, text=xml_body)
                )
                return await loader.fetch_departments_from_single_domain(DOMAIN)

        result = asyncio.run(_run())

        assert len(result) == 2
        for dept in result:
            assert dept["iiko_source_domain"] == "sandy-co-co.iiko.it"

    def test_source_domain_is_host_only_not_full_url(self, loader) -> None:
        """If the URL has a path/port, only the hostname is stored."""
        xml_body = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>z</id><name>Z</name><type>DEPARTMENT</type>
            </corporateItemDto>
        </departments>"""
        url = "http://other-host.example:9000"

        async def _run() -> list[dict]:
            with respx.mock() as router:
                router.get(f"{url}/resto/api/auth").mock(
                    return_value=httpx.Response(200, text="t")
                )
                router.get(f"{url}/resto/api/corporation/departments").mock(
                    return_value=httpx.Response(200, text=xml_body)
                )
                return await loader.fetch_departments_from_single_domain(url)

        result = asyncio.run(_run())
        assert result[0]["iiko_source_domain"] == "other-host.example"
