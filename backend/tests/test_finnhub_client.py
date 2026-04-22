"""Tests for Finnhub provider wrapper."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from market_screener.providers.exceptions import (
    ProviderConfigError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderSchemaError,
)
from market_screener.providers.finnhub import FinnhubClient
from market_screener.providers.rate_limit import ProviderRateLimiter
from market_screener.providers.retry import RetryPolicy


def _build_client(handler: Callable[[httpx.Request], httpx.Response]) -> FinnhubClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://finnhub.io/api/v1",
        timeout=httpx.Timeout(timeout=15, connect=5, read=12),
    )
    return FinnhubClient(api_key="demo-finnhub-key", client=http_client)


def test_get_quote_builds_required_path_and_query_params() -> None:
    captured_path = ""
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_path
        captured_path = request.url.path
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json={"c": 190.2, "pc": 189.1})

    client = _build_client(handler)

    payload = client.get_quote("AAPL")

    assert payload["c"] == 190.2
    assert captured_path == "/api/v1/quote"
    assert captured_params["symbol"] == "AAPL"
    assert captured_params["token"] == "demo-finnhub-key"


def test_get_stock_candles_builds_expected_query_params() -> None:
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json={"s": "ok", "o": [1.0], "h": [1.2], "l": [0.9], "c": [1.1]})

    client = _build_client(handler)

    payload = client.get_stock_candles(
        "AAPL",
        resolution="D",
        from_unix=1704067200,
        to_unix=1704672000,
    )

    assert payload["s"] == "ok"
    assert captured_params["resolution"] == "D"
    assert captured_params["from"] == "1704067200"
    assert captured_params["to"] == "1704672000"


def test_http_429_is_mapped_to_rate_limit_error() -> None:
    client = _build_client(
        lambda _request: httpx.Response(429, json={"error": "Too many requests"})
    )

    with pytest.raises(ProviderRateLimitError):
        client.get_quote("AAPL")


def test_error_payload_is_mapped_to_provider_response_error() -> None:
    client = _build_client(lambda _request: httpx.Response(200, json={"error": "Invalid API key"}))

    with pytest.raises(ProviderResponseError):
        client.get_quote("AAPL")


def test_company_news_requires_array_payload() -> None:
    client = _build_client(lambda _request: httpx.Response(200, json={"headline": "bad-shape"}))

    with pytest.raises(ProviderSchemaError):
        client.get_company_news("AAPL", from_date="2026-04-01", to_date="2026-04-22")


def test_missing_api_key_raises_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        FinnhubClient(api_key="")


def test_get_quote_retries_on_503_before_success() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "temporary overload"})
        return httpx.Response(200, json={"c": 120.5})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="https://finnhub.io/api/v1")
    client = FinnhubClient(
        api_key="demo-finnhub-key",
        client=http_client,
        retry_policy=RetryPolicy(attempts=3, backoff_seconds=(0.0,), jitter_seconds=0.0),
    )

    payload = client.get_quote("AAPL")

    assert payload["c"] == 120.5
    assert attempts == 3


def test_get_quote_raises_when_local_quota_is_exhausted() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"c": 101.0}))
    http_client = httpx.Client(transport=transport, base_url="https://finnhub.io/api/v1")
    client = FinnhubClient(
        api_key="demo-finnhub-key",
        client=http_client,
        retry_policy=RetryPolicy(attempts=1, backoff_seconds=(1.0,)),
        rate_limiter=ProviderRateLimiter("finnhub", max_requests_per_minute=1, reserve_ratio=0.0),
    )

    first = client.get_quote("AAPL")
    assert first["c"] == 101.0

    with pytest.raises(ProviderQuotaExceededError):
        client.get_quote("AAPL")
