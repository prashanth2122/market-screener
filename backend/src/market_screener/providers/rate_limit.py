"""In-memory provider rate-limit guard with quota counters."""

from __future__ import annotations

from math import floor
from threading import Lock
from time import monotonic
from typing import Callable

from market_screener.providers.exceptions import ProviderQuotaExceededError


class ProviderRateLimiter:
    """Token-bucket limiter with counters for provider quota visibility."""

    def __init__(
        self,
        provider_name: str,
        *,
        max_requests_per_minute: int,
        reserve_ratio: float = 0.1,
        now_fn: Callable[[], float] = monotonic,
    ) -> None:
        if max_requests_per_minute < 1:
            raise ValueError("max_requests_per_minute must be >= 1")
        if not 0 <= reserve_ratio < 1:
            raise ValueError("reserve_ratio must be in range [0, 1)")

        self.provider_name = provider_name
        self.max_requests_per_minute = max_requests_per_minute
        self.reserve_ratio = reserve_ratio
        self._effective_capacity = max(1, int(max_requests_per_minute * (1 - reserve_ratio)))
        self._refill_rate_per_second = self._effective_capacity / 60.0
        self._tokens = float(self._effective_capacity)
        self._now_fn = now_fn
        self._last_refill = now_fn()
        self._lock = Lock()

        self._total_attempts = 0
        self._success_count = 0
        self._failure_count = 0
        self._rate_limited_count = 0
        self._quota_blocked_count = 0
        self._latency_total_ms = 0.0
        self._latency_samples = 0

    def acquire(self) -> None:
        """Consume one token or raise when quota is depleted."""

        with self._lock:
            self._refill_tokens()
            if self._tokens < 1.0:
                self._quota_blocked_count += 1
                raise ProviderQuotaExceededError(f"{self.provider_name}_quota_exhausted")

            self._tokens -= 1.0
            self._total_attempts += 1

    def record_response(self, status_code: int, latency_ms: float) -> None:
        """Record response-level counters and latency samples."""

        with self._lock:
            self._latency_total_ms += latency_ms
            self._latency_samples += 1
            if 200 <= status_code < 400:
                self._success_count += 1
            else:
                self._failure_count += 1
                if status_code == 429:
                    self._rate_limited_count += 1

    def record_exception(self) -> None:
        """Record transport/request exceptions."""

        with self._lock:
            self._failure_count += 1

    def snapshot(self) -> dict[str, float | int | str]:
        """Return current quota and counter values."""

        with self._lock:
            self._refill_tokens()
            avg_latency = (
                self._latency_total_ms / self._latency_samples if self._latency_samples else 0.0
            )
            return {
                "provider": self.provider_name,
                "max_requests_per_minute": self.max_requests_per_minute,
                "effective_capacity": self._effective_capacity,
                "quota_remaining": max(0, floor(self._tokens)),
                "total_attempts": self._total_attempts,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "rate_limited_count": self._rate_limited_count,
                "quota_blocked_count": self._quota_blocked_count,
                "avg_latency_ms": round(avg_latency, 2),
            }

    def _refill_tokens(self) -> None:
        now = self._now_fn()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed <= 0:
            return

        self._tokens = min(
            self._effective_capacity,
            self._tokens + elapsed * self._refill_rate_per_second,
        )
        self._last_refill = now
