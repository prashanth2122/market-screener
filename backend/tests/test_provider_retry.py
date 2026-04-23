"""Tests for shared provider retry policy behavior."""

from __future__ import annotations

import httpx
import pytest

from market_screener.providers.retry import (
    RetryPolicy,
    parse_backoff_seconds,
    request_with_retry,
)


def test_request_with_retry_retries_on_timeout_then_succeeds() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    policy = RetryPolicy(attempts=3, backoff_seconds=(1.0, 2.0, 4.0))

    response = request_with_retry(
        client,
        "GET",
        "/resource",
        policy=policy,
        sleep_fn=delays.append,
        random_fn=lambda: 0.0,
    )

    assert response.status_code == 200
    assert attempts == 3
    assert delays == [1.0, 2.0]


def test_request_with_retry_retries_on_retryable_status_then_succeeds() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    policy = RetryPolicy(attempts=3, backoff_seconds=(1.0, 2.0, 4.0))

    response = request_with_retry(
        client,
        "GET",
        "/resource",
        policy=policy,
        sleep_fn=lambda _seconds: None,
        random_fn=lambda: 0.0,
    )

    assert response.status_code == 200
    assert attempts == 3


def test_request_with_retry_does_not_retry_non_retryable_4xx() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    policy = RetryPolicy(attempts=3, backoff_seconds=(1.0, 2.0, 4.0))

    response = request_with_retry(
        client,
        "GET",
        "/resource",
        policy=policy,
        sleep_fn=lambda _seconds: None,
        random_fn=lambda: 0.0,
    )

    assert response.status_code == 401
    assert attempts == 1


def test_request_with_retry_raises_after_exhausting_timeout_retries() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("still timing out")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    policy = RetryPolicy(attempts=3, backoff_seconds=(1.0, 2.0, 4.0))

    with pytest.raises(httpx.ReadTimeout):
        request_with_retry(
            client,
            "GET",
            "/resource",
            policy=policy,
            sleep_fn=lambda _seconds: None,
            random_fn=lambda: 0.0,
        )


def test_parse_backoff_seconds_uses_default_when_invalid() -> None:
    assert parse_backoff_seconds("bad, ,0,-1") == (1.0, 2.0, 4.0)
