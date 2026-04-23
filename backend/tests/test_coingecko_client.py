"""Tests for CoinGecko provider wrapper."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from market_screener.providers.coingecko import CoinGeckoClient
from market_screener.providers.exceptions import (
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderSchemaError,
)
from market_screener.providers.rate_limit import ProviderRateLimiter
from market_screener.providers.retry import RetryPolicy


def _build_client(handler: Callable[[httpx.Request], httpx.Response]) -> CoinGeckoClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://api.coingecko.com/api/v3",
        timeout=httpx.Timeout(timeout=15, connect=5, read=12),
    )
    return CoinGeckoClient(client=http_client)


def test_get_simple_price_builds_expected_query_params() -> None:
    captured_path = ""
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_path
        captured_path = request.url.path
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json={"bitcoin": {"usd": 67000.0}})

    client = _build_client(handler)

    payload = client.get_simple_price(ids="bitcoin", vs_currencies="usd")

    assert payload["bitcoin"]["usd"] == 67000.0
    assert captured_path == "/api/v3/simple/price"
    assert captured_params["ids"] == "bitcoin"
    assert captured_params["vs_currencies"] == "usd"
    assert captured_params["include_24hr_change"] == "true"


def test_get_coin_markets_includes_demo_api_key_param_when_configured() -> None:
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json=[{"id": "bitcoin", "symbol": "btc"}])

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://api.coingecko.com/api/v3",
        timeout=httpx.Timeout(timeout=15, connect=5, read=12),
    )
    client = CoinGeckoClient(api_key="demo-key", client=http_client)

    payload = client.get_coin_markets(vs_currency="usd")

    assert payload[0]["id"] == "bitcoin"
    assert captured_params["x_cg_demo_api_key"] == "demo-key"


def test_http_429_is_mapped_to_rate_limit_error() -> None:
    client = _build_client(
        lambda _request: httpx.Response(429, json={"status": {"error_message": "rate limited"}})
    )

    with pytest.raises(ProviderRateLimitError):
        client.get_simple_price(ids="bitcoin", vs_currencies="usd")


def test_error_payload_is_mapped_to_provider_response_error() -> None:
    client = _build_client(
        lambda _request: httpx.Response(200, json={"status": {"error_message": "bad request"}})
    )

    with pytest.raises(ProviderResponseError):
        client.get_simple_price(ids="bitcoin", vs_currencies="usd")


def test_coin_markets_requires_array_payload() -> None:
    client = _build_client(lambda _request: httpx.Response(200, json={"id": "bitcoin"}))

    with pytest.raises(ProviderSchemaError):
        client.get_coin_markets(vs_currency="usd")


def test_get_simple_price_raises_when_local_quota_is_exhausted() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"bitcoin": {"usd": 100.0}})
    )
    http_client = httpx.Client(transport=transport, base_url="https://api.coingecko.com/api/v3")
    client = CoinGeckoClient(
        client=http_client,
        retry_policy=RetryPolicy(attempts=1, backoff_seconds=(1.0,)),
        rate_limiter=ProviderRateLimiter("coingecko", max_requests_per_minute=1, reserve_ratio=0.0),
    )

    first = client.get_simple_price(ids="bitcoin", vs_currencies="usd")
    assert first["bitcoin"]["usd"] == 100.0

    with pytest.raises(ProviderQuotaExceededError):
        client.get_simple_price(ids="bitcoin", vs_currencies="usd")
