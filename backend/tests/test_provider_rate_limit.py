"""Tests for provider rate-limit guard behavior."""

from __future__ import annotations

from market_screener.providers.exceptions import ProviderQuotaExceededError
from market_screener.providers.rate_limit import ProviderRateLimiter


def test_rate_limiter_blocks_when_quota_is_exhausted() -> None:
    now = 1000.0

    def now_fn() -> float:
        return now

    limiter = ProviderRateLimiter(
        "test_provider",
        max_requests_per_minute=2,
        reserve_ratio=0.0,
        now_fn=now_fn,
    )

    limiter.acquire()
    limiter.acquire()

    try:
        limiter.acquire()
        assert False, "expected quota exhaustion"
    except ProviderQuotaExceededError:
        pass

    snapshot = limiter.snapshot()
    assert snapshot["total_attempts"] == 2
    assert snapshot["quota_blocked_count"] == 1


def test_rate_limiter_refills_tokens_over_time() -> None:
    clock = {"value": 1000.0}

    def now_fn() -> float:
        return clock["value"]

    limiter = ProviderRateLimiter(
        "test_provider",
        max_requests_per_minute=2,
        reserve_ratio=0.0,
        now_fn=now_fn,
    )

    limiter.acquire()
    limiter.acquire()

    clock["value"] += 30.0
    limiter.acquire()

    snapshot = limiter.snapshot()
    assert snapshot["total_attempts"] == 3
    assert snapshot["quota_blocked_count"] == 0


def test_rate_limiter_counters_track_success_failure_and_latency() -> None:
    limiter = ProviderRateLimiter(
        "test_provider",
        max_requests_per_minute=10,
        reserve_ratio=0.0,
    )

    limiter.record_response(status_code=200, latency_ms=100.0)
    limiter.record_response(status_code=503, latency_ms=200.0)
    limiter.record_response(status_code=429, latency_ms=300.0)
    limiter.record_exception()

    snapshot = limiter.snapshot()
    assert snapshot["success_count"] == 1
    assert snapshot["failure_count"] == 3
    assert snapshot["rate_limited_count"] == 1
    assert snapshot["avg_latency_ms"] == 200.0
