"""Unit tests for IikoNomenclatureLoaderService helpers.

Covers the pure helpers (`_domain_host`, `_to_decimal_str`) — the actual
upsert paths require a live DB connection and are exercised by the
integration smoke after `POST /api/menu/sync`.
"""

from __future__ import annotations

import pytest

from app.services.iiko_nomenclature_loader import _domain_host, _to_decimal_str

pytestmark = pytest.mark.unit


class TestDomainHost:
    def test_full_https_url(self) -> None:
        assert _domain_host("https://sandy-co-co.iiko.it") == "sandy-co-co.iiko.it"

    def test_http_with_path(self) -> None:
        assert _domain_host("http://example.com/api/v2") == "example.com"

    def test_bare_hostname(self) -> None:
        assert _domain_host("example.com") == "example.com"

    def test_lowercases_host(self) -> None:
        assert _domain_host("https://EXAMPLE.com") == "example.com"


class TestToDecimalStr:
    def test_none_passes_through(self) -> None:
        assert _to_decimal_str(None) is None

    def test_zero_becomes_string_zero(self) -> None:
        assert _to_decimal_str(0) == "0"

    def test_integer_value(self) -> None:
        assert _to_decimal_str(150) == "150"

    def test_float_with_meaningful_decimals(self) -> None:
        # 0.7% loss must round-trip cleanly
        assert _to_decimal_str(0.007) == "0.007"

    def test_float_trailing_zeros_stripped(self) -> None:
        assert _to_decimal_str(1.50) == "1.5"

    def test_float_with_high_precision(self) -> None:
        # 1.7250 kg — iiko-style unit weight
        assert _to_decimal_str(1.725) == "1.725"

    def test_invalid_string_returns_none(self) -> None:
        assert _to_decimal_str("not-a-number") is None
