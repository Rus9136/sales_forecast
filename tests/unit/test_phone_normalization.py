"""Unit tests for `normalize_phone` — UI auth phone normalization."""

from __future__ import annotations

import pytest

from app.auth_ui import normalize_phone


pytestmark = pytest.mark.unit


class TestNormalizePhone:
    def test_strips_spaces_parens_dashes(self):
        assert normalize_phone("+7 (777) 123-45-67") == "77771234567"

    def test_keeps_only_digits(self):
        assert normalize_phone("77001234567") == "77001234567"

    def test_legacy_8_prefix_is_rewritten_to_7(self):
        # Kazakhstan/Russia legacy: 8XXXXXXXXXX → 7XXXXXXXXXX
        assert normalize_phone("87001234567") == "77001234567"

    def test_8_prefix_only_for_11_digit_numbers(self):
        # 10-digit number starting with 8 must NOT be rewritten — only the
        # specific 11-digit legacy prefix is.
        assert normalize_phone("8001234567") == "8001234567"

    def test_strips_plus_sign(self):
        assert normalize_phone("+77771234567") == "77771234567"


class TestNormalizePhoneRejects:
    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            normalize_phone("")

    def test_only_punctuation_raises(self):
        with pytest.raises(ValueError):
            normalize_phone("+- ()")

    def test_too_short_raises(self):
        # 9 digits — below the 10..15 bound.
        with pytest.raises(ValueError):
            normalize_phone("123456789")

    def test_too_long_raises(self):
        # 16 digits — above the 10..15 bound.
        with pytest.raises(ValueError):
            normalize_phone("1234567890123456")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            normalize_phone(None)  # type: ignore[arg-type]
