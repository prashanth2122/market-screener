"""Tests for Marketaux news provider wrapper."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
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
from market_screener.providers.marketaux import MarketauxNewsClient
from market_screener.providers.rate_limit import ProviderRateLimiter
from market_screener.providers.retry import RetryPolicy


def _build_client(handler: Callable[[httpx.Request], httpx.Response]) -> MarketauxNewsClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://api.marketaux.com/v1",
        timeout=httpx.Timeout(timeout=15, connect=5, read=12),
    )
    return MarketauxNewsClient(api_token="demo-marketaux-token", client=http_client)


def test_get_news_builds_expected_path_and_query_params() -> None:
    captured_path = ""
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_path
        captured_path = request.url.path
        captured_params.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "published_at": "2026-04-23T00:00:00Z",
                        "title": "Sample headline",
                    }
                ]
            },
        )

    client = _build_client(handler)

    payload = client.get_news(
        "AAPL",
        limit=3,
        language="en",
        published_after=datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
    )

    assert payload[0]["title"] == "Sample headline"
    assert captured_path == "/v1/news/all"
    assert captured_params["symbols"] == "AAPL"
    assert captured_params["limit"] == "3"
    assert captured_params["language"] == "en"
    assert captured_params["published_after"] == "2026-04-22T00:00:00Z"
    assert captured_params["api_token"] == "demo-marketaux-token"


def test_error_payload_is_mapped_to_provider_response_error() -> None:
    client = _build_client(
        lambda _request: httpx.Response(
            200,
            json={"error": {"code": "invalid_api_token", "message": "Invalid API token"}},
        )
    )

    with pytest.raises(ProviderResponseError):
        client.get_news("AAPL", limit=1)


def test_news_payload_requires_data_list() -> None:
    client = _build_client(lambda _request: httpx.Response(200, json={"meta": {}}))

    with pytest.raises(ProviderSchemaError):
        client.get_news("AAPL", limit=1)


def test_http_429_is_mapped_to_rate_limit_error() -> None:
    client = _build_client(lambda _request: httpx.Response(429, json={"error": "Rate limited"}))

    with pytest.raises(ProviderRateLimitError):
        client.get_news("AAPL", limit=1)


def test_missing_api_token_raises_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        MarketauxNewsClient(api_token="")


def test_marketaux_client_retries_on_503_before_success() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "temporary overload"})
        return httpx.Response(
            200,
            json={"data": [{"published_at": "2026-04-23T00:00:00Z", "title": "Recovered"}]},
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="https://api.marketaux.com/v1")
    client = MarketauxNewsClient(
        api_token="demo-marketaux-token",
        client=http_client,
        retry_policy=RetryPolicy(attempts=3, backoff_seconds=(0.0,), jitter_seconds=0.0),
    )

    payload = client.get_news("AAPL", limit=1)

    assert payload[0]["title"] == "Recovered"
    assert attempts == 3


def test_marketaux_client_raises_when_local_quota_is_exhausted() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, json={"data": [{"published_at": "2026-04-23T00:00:00Z", "title": "One"}]}
        )
    )
    http_client = httpx.Client(transport=transport, base_url="https://api.marketaux.com/v1")
    client = MarketauxNewsClient(
        api_token="demo-marketaux-token",
        client=http_client,
        retry_policy=RetryPolicy(attempts=1, backoff_seconds=(1.0,)),
        rate_limiter=ProviderRateLimiter("marketaux", max_requests_per_minute=1, reserve_ratio=0.0),
    )

    first = client.get_news("AAPL", limit=1)
    assert first[0]["title"] == "One"

    with pytest.raises(ProviderQuotaExceededError):
        client.get_news("AAPL", limit=1)
