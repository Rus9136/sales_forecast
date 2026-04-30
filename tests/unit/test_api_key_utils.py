"""Unit tests for API key generation, hashing, verification and parsing."""

from __future__ import annotations

import hashlib

import pytest

from app.auth import (
    extract_key_id_from_api_key,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)


pytestmark = pytest.mark.unit


class TestGenerateApiKey:
    def test_returns_key_id_and_full_key(self):
        key_id, full_key = generate_api_key()
        assert isinstance(key_id, str)
        assert isinstance(full_key, str)

    def test_full_key_has_sf_prefix(self):
        _, full_key = generate_api_key()
        assert full_key.startswith("sf_")

    def test_full_key_starts_with_key_id(self):
        key_id, full_key = generate_api_key()
        # Full key format: sf_<key_id>_<secret>
        assert full_key.startswith(f"sf_{key_id}_")

    def test_two_calls_produce_different_keys(self):
        a_id, a_full = generate_api_key()
        b_id, b_full = generate_api_key()
        assert a_id != b_id
        assert a_full != b_full

    def test_key_id_is_url_safe(self):
        key_id, _ = generate_api_key()
        # token_urlsafe uses [A-Za-z0-9_-]
        assert all(c.isalnum() or c in "_-" for c in key_id)


class TestHashAndVerify:
    def test_hash_is_sha256_hex(self):
        digest = hash_api_key("secret-value")
        assert digest == hashlib.sha256(b"secret-value").hexdigest()
        assert len(digest) == 64

    def test_hash_is_deterministic(self):
        assert hash_api_key("abc") == hash_api_key("abc")

    def test_hash_differs_for_different_inputs(self):
        assert hash_api_key("a") != hash_api_key("b")

    def test_verify_roundtrip(self):
        api_key = "sf_test_key_value"
        stored = hash_api_key(api_key)
        assert verify_api_key(api_key, stored) is True

    def test_verify_fails_for_wrong_key(self):
        stored = hash_api_key("expected")
        assert verify_api_key("provided", stored) is False

    def test_verify_is_case_sensitive(self):
        stored = hash_api_key("Secret")
        assert verify_api_key("secret", stored) is False


class TestExtractKeyId:
    def test_returns_key_id_from_freshly_generated_key(self):
        key_id, full_key = generate_api_key()
        assert extract_key_id_from_api_key(full_key) == key_id

    def test_roundtrip_holds_for_many_random_keys(self):
        """Regression guard: no random key from generate_api_key may fail to parse.

        The previous parser split on '_' and broke for ~98.5% of freshly
        generated keys because secrets.token_urlsafe produces a random
        number of '_'. Run a batch to catch any regression that re-introduces
        the underscore-counting assumption.
        """
        for _ in range(200):
            key_id, full_key = generate_api_key()
            assert extract_key_id_from_api_key(full_key) == key_id

    def test_returns_none_when_prefix_missing(self):
        assert extract_key_id_from_api_key("no_prefix_here") is None

    def test_returns_none_for_empty_input(self):
        assert extract_key_id_from_api_key("") is None

    def test_returns_none_for_just_prefix(self):
        assert extract_key_id_from_api_key("sf_") is None

    def test_returns_none_when_too_short_for_full_key_id(self):
        # 31 chars after `sf_` — one short of the 32-char key_id.
        assert extract_key_id_from_api_key("sf_" + "a" * 31) is None

    def test_returns_none_when_separator_missing_after_key_id(self):
        # 32 chars + non-underscore + secret → invalid format.
        assert extract_key_id_from_api_key("sf_" + "a" * 32 + "Xsecret") is None

    def test_returns_none_when_secret_missing(self):
        # 32 chars + '_' but nothing after → no secret.
        assert extract_key_id_from_api_key("sf_" + "a" * 32 + "_") is None

    def test_accepts_known_production_key_format(self):
        # The currently active production key uses key_id "1WIK_p9-x_qoBDgHkm5hqqKnjolZ0xF5".
        # This guards backward compatibility of the parser change.
        full_key = "sf_1WIK_p9-x_qoBDgHkm5hqqKnjolZ0xF5_" + "s" * 43
        assert extract_key_id_from_api_key(full_key) == "1WIK_p9-x_qoBDgHkm5hqqKnjolZ0xF5"
