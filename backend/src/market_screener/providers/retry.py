"""Shared HTTP retry policy for provider clients."""

from __future__ import annotations

from dataclasses import dataclass
from random import random
from time import perf_counter
from time import sleep as default_sleep
from typing import Callable

import httpx

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, httpx.TransportError)


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for bounded retry with exponential backoff."""

    attempts: int
    backoff_seconds: tuple[float, ...]
    jitter_seconds: float = 0.2

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be >= 1")
        if not self.backoff_seconds:
            raise ValueError("backoff_seconds must not be empty")

    @classmethod
    def from_settings(cls, attempts: int, backoff_csv: str) -> "RetryPolicy":
        """Build retry policy from runtime settings values."""

        return cls(
            attempts=attempts,
            backoff_seconds=parse_backoff_seconds(backoff_csv),
        )

    def delay_for_attempt(self, attempt_number: int) -> float:
        """Return delay for a given 1-based attempt number."""

        index = min(max(attempt_number - 1, 0), len(self.backoff_seconds) - 1)
        return self.backoff_seconds[index]


def parse_backoff_seconds(backoff_csv: str) -> tuple[float, ...]:
    """Parse comma-separated backoff values into a normalized tuple."""

    values: list[float] = []
    for raw in backoff_csv.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            parsed = float(token)
        except ValueError:
            continue
        if parsed > 0:
            values.append(parsed)

    return tuple(values) if values else (1.0, 2.0, 4.0)


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: dict[str, str | int | float] | None = None,
    policy: RetryPolicy,
    sleep_fn: Callable[[float], None] = default_sleep,
    random_fn: Callable[[], float] = random,
    on_attempt_start: Callable[[], None] | None = None,
    on_attempt_result: (
        Callable[[httpx.Response | None, Exception | None, float], None] | None
    ) = None,
) -> httpx.Response:
    """Send an HTTP request with retry policy for transient failures."""

    for attempt in range(1, policy.attempts + 1):
        if on_attempt_start:
            on_attempt_start()

        started = perf_counter()
        try:
            response = client.request(method, url, params=params)
        except _RETRYABLE_EXCEPTIONS as exc:
            elapsed_ms = (perf_counter() - started) * 1000
            if on_attempt_result:
                on_attempt_result(None, exc, elapsed_ms)
            if attempt == policy.attempts:
                raise
            _sleep_for_next_attempt(policy, attempt, sleep_fn, random_fn)
            continue

        elapsed_ms = (perf_counter() - started) * 1000
        if on_attempt_result:
            on_attempt_result(response, None, elapsed_ms)

        if response.status_code in RETRYABLE_STATUS_CODES and attempt < policy.attempts:
            _sleep_for_next_attempt(policy, attempt, sleep_fn, random_fn)
            continue

        return response

    raise RuntimeError("request retry loop exhausted unexpectedly")


def _sleep_for_next_attempt(
    policy: RetryPolicy,
    attempt: int,
    sleep_fn: Callable[[float], None],
    random_fn: Callable[[], float],
) -> None:
    base_delay = policy.delay_for_attempt(attempt)
    jitter = random_fn() * policy.jitter_seconds
    sleep_fn(base_delay + jitter)
