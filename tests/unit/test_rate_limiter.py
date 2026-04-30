"""Unit tests for `InMemoryRateLimiter`.

Time advances are driven by `freezegun` because the limiter calls
`datetime.utcnow()` directly. `tick(seconds)` is the only piece of state we
manipulate; nothing else here touches the database or the network.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from app.auth import InMemoryRateLimiter


pytestmark = pytest.mark.unit


@pytest.fixture()
def limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter()


@pytest.fixture()
def frozen():
    """Freeze time at a known instant, yield the controller for tick advancing."""
    with freeze_time("2026-04-30 12:00:00") as f:
        yield f


class TestBasicAllow:
    def test_first_request_is_allowed(self, limiter, frozen):
        assert limiter.check_and_record("k1", 10, 100, 1000) is True

    def test_independent_keys_have_independent_buckets(self, limiter, frozen):
        for _ in range(5):
            assert limiter.check_and_record("a", 5, 100, 1000) is True
        # 'a' is now full at the minute window
        assert limiter.check_and_record("a", 5, 100, 1000) is False
        # 'b' is untouched
        assert limiter.check_and_record("b", 5, 100, 1000) is True


class TestMinuteWindow:
    def test_blocks_at_minute_limit(self, limiter, frozen):
        for _ in range(3):
            assert limiter.check_and_record("k", 3, 100, 1000) is True
        assert limiter.check_and_record("k", 3, 100, 1000) is False

    def test_allows_again_after_minute_passes(self, limiter, frozen):
        for _ in range(3):
            limiter.check_and_record("k", 3, 100, 1000)
        # Advance 61 seconds — minute window is now empty.
        frozen.tick(timedelta(seconds=61))
        assert limiter.check_and_record("k", 3, 100, 1000) is True


class TestHourWindow:
    def test_blocks_at_hour_limit_even_when_minute_window_clear(self, limiter, frozen):
        # Spread 5 requests across the hour, one every 10 minutes — minute
        # window never has more than 1 entry, but hour window fills.
        for _ in range(5):
            assert limiter.check_and_record("k", 100, 5, 1000) is True
            frozen.tick(timedelta(minutes=10))
        # Still inside the hour window — 6th request must be rejected.
        frozen.tick(timedelta(seconds=-1))  # back inside the last 60 minutes
        assert limiter.check_and_record("k", 100, 5, 1000) is False


class TestDayWindow:
    def test_blocks_at_day_limit(self, limiter, frozen):
        # Cheaper test: small day limit, advance just past the hour cutoff so
        # entries stay in the day bucket but leave the hour bucket.
        for i in range(3):
            assert limiter.check_and_record("k", 100, 100, 3) is True
            frozen.tick(timedelta(hours=2))
        # Day count is 3, day_limit is 3 → reject.
        assert limiter.check_and_record("k", 100, 100, 3) is False


class TestPruning:
    def test_entries_older_than_24h_are_pruned(self, limiter, frozen):
        limiter.check_and_record("k", 100, 100, 2)  # day=1
        frozen.tick(timedelta(hours=25))            # entry now older than 24h
        # The old entry is pruned the next time we touch the key, so the day
        # bucket is empty again and we should be allowed twice in a row.
        assert limiter.check_and_record("k", 100, 100, 2) is True
        assert limiter.check_and_record("k", 100, 100, 2) is True
        assert limiter.check_and_record("k", 100, 100, 2) is False

    def test_uses_real_utc_clock(self, limiter):
        """Sanity check — without freezing time, the limiter still works."""
        before = datetime.utcnow()
        assert limiter.check_and_record("k_real", 1, 1, 1) is True
        # Internal deque got exactly one timestamp, recorded at ~now.
        recorded = limiter._requests["k_real"][0]
        assert before <= recorded <= datetime.utcnow()
