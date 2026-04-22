"""Tests for per-user rate limiter."""

import pytest
from fastapi import HTTPException

from app.services import user_rate_limit
from app.services.user_rate_limit import (
    check_user_rate_limit,
    clear_user_failures,
    record_user_failure,
    prune_stale,
)


@pytest.fixture(autouse=True)
def clear_state():
    """Ensure each test starts with empty rate-limit state."""
    user_rate_limit._buckets.clear()
    yield
    user_rate_limit._buckets.clear()


class TestCheckUserRateLimit:
    def test_allows_requests_under_limit(self):
        for _ in range(5):
            check_user_rate_limit(
                user_id=1, bucket="test", max_requests=5, window_seconds=60
            )

    def test_blocks_at_limit(self):
        for _ in range(3):
            check_user_rate_limit(
                user_id=1, bucket="test", max_requests=3, window_seconds=60
            )
        with pytest.raises(HTTPException) as exc:
            check_user_rate_limit(
                user_id=1, bucket="test", max_requests=3, window_seconds=60
            )
        assert exc.value.status_code == 429
        assert "Retry-After" in exc.value.headers

    def test_separate_users_do_not_cross_throttle(self):
        for _ in range(3):
            check_user_rate_limit(
                user_id=1, bucket="test", max_requests=3, window_seconds=60
            )
        # user 2 should not be affected
        check_user_rate_limit(
            user_id=2, bucket="test", max_requests=3, window_seconds=60
        )

    def test_separate_buckets_do_not_cross_throttle(self):
        for _ in range(3):
            check_user_rate_limit(
                user_id=1, bucket="bucket_a", max_requests=3, window_seconds=60
            )
        # different bucket for same user should still pass
        check_user_rate_limit(
            user_id=1, bucket="bucket_b", max_requests=3, window_seconds=60
        )

    def test_custom_message_is_returned(self):
        for _ in range(2):
            check_user_rate_limit(
                user_id=1,
                bucket="test",
                max_requests=2,
                window_seconds=60,
                message="custom-message",
            )
        with pytest.raises(HTTPException) as exc:
            check_user_rate_limit(
                user_id=1,
                bucket="test",
                max_requests=2,
                window_seconds=60,
                message="custom-message",
            )
        assert exc.value.detail == "custom-message"

    def test_expired_entries_are_dropped(self, monkeypatch):
        # Seed timestamps 2 hours in the past
        import time as time_module

        real_time = time_module.time
        fake_now = {"value": real_time() - 7200}

        monkeypatch.setattr(user_rate_limit.time, "time", lambda: fake_now["value"])
        for _ in range(5):
            check_user_rate_limit(
                user_id=1, bucket="test", max_requests=5, window_seconds=60
            )

        fake_now["value"] = real_time()
        check_user_rate_limit(
            user_id=1, bucket="test", max_requests=5, window_seconds=60
        )


class TestRecordUserFailure:
    def test_only_raises_after_max_failures(self):
        for _ in range(4):
            record_user_failure(
                user_id=1, bucket="mfa", max_failures=5, window_seconds=900
            )
        with pytest.raises(HTTPException) as exc:
            record_user_failure(
                user_id=1, bucket="mfa", max_failures=5, window_seconds=900
            )
        assert exc.value.status_code == 429

    def test_clear_user_failures_resets_counter(self):
        for _ in range(4):
            record_user_failure(
                user_id=1, bucket="mfa", max_failures=5, window_seconds=900
            )
        clear_user_failures(user_id=1, bucket="mfa")
        # Should now allow 4 more before hitting the limit on the 5th
        for _ in range(4):
            record_user_failure(
                user_id=1, bucket="mfa", max_failures=5, window_seconds=900
            )

    def test_clear_nonexistent_bucket_is_noop(self):
        clear_user_failures(user_id=999, bucket="never-seen")


class TestPruneStale:
    def test_prune_removes_old_buckets(self, monkeypatch):
        import time as time_module

        real_time = time_module.time
        fake_now = {"value": real_time() - 10000}
        monkeypatch.setattr(user_rate_limit.time, "time", lambda: fake_now["value"])

        check_user_rate_limit(
            user_id=1, bucket="stale", max_requests=10, window_seconds=60
        )

        fake_now["value"] = real_time()
        pruned = prune_stale()
        assert pruned >= 1
