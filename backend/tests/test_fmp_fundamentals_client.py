"""Tests for FMP fundamentals provider wrapper."""

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
from market_screener.providers.fmp import FMPFundamentalsClient
from market_screener.providers.rate_limit import ProviderRateLimiter
from market_screener.providers.retry import RetryPolicy


def _build_client(handler: Callable[[httpx.Request], httpx.Response]) -> FMPFundamentalsClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://financialmodelingprep.com/api/v3",
        timeout=httpx.Timeout(timeout=15, connect=5, read=12),
    )
    return FMPFundamentalsClient(api_key="demo-fmp-key", client=http_client)


def test_income_statement_builds_expected_path_and_query_params() -> None:
    captured_path = ""
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_path
        captured_path = request.url.path
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json=[{"date": "2025-12-31", "revenue": 1000}])

    client = _build_client(handler)

    payload = client.get_income_statements("AAPL", period="annual", limit=2)

    assert payload[0]["revenue"] == 1000
    assert captured_path == "/api/v3/income-statement/AAPL"
    assert captured_params["period"] == "annual"
    assert captured_params["limit"] == "2"
    assert captured_params["apikey"] == "demo-fmp-key"


def test_error_payload_is_mapped_to_provider_response_error() -> None:
    client = _build_client(lambda _request: httpx.Response(200, json={"error": "Invalid API key"}))

    with pytest.raises(ProviderResponseError):
        client.get_income_statements("AAPL", period="annual", limit=1)


def test_income_statement_requires_array_payload() -> None:
    client = _build_client(lambda _request: httpx.Response(200, json={"date": "2025-12-31"}))

    with pytest.raises(ProviderSchemaError):
        client.get_income_statements("AAPL", period="annual", limit=1)


def test_http_429_is_mapped_to_rate_limit_error() -> None:
    client = _build_client(
        lambda _request: httpx.Response(429, json={"error": "Too many requests"})
    )

    with pytest.raises(ProviderRateLimitError):
        client.get_balance_sheet_statements("AAPL", period="annual", limit=1)


def test_missing_api_key_raises_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        FMPFundamentalsClient(api_key="")


def test_fmp_client_retries_on_503_before_success() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "temporary overload"})
        return httpx.Response(200, json=[{"date": "2025-12-31", "marketCap": 5000}])

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport, base_url="https://financialmodelingprep.com/api/v3"
    )
    client = FMPFundamentalsClient(
        api_key="demo-fmp-key",
        client=http_client,
        retry_policy=RetryPolicy(attempts=3, backoff_seconds=(0.0,), jitter_seconds=0.0),
    )

    payload = client.get_key_metrics("AAPL", period="annual", limit=1)

    assert payload[0]["marketCap"] == 5000
    assert attempts == 3


def test_fmp_client_raises_when_local_quota_is_exhausted() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json=[{"date": "2025-12-31"}])
    )
    http_client = httpx.Client(
        transport=transport, base_url="https://financialmodelingprep.com/api/v3"
    )
    client = FMPFundamentalsClient(
        api_key="demo-fmp-key",
        client=http_client,
        retry_policy=RetryPolicy(attempts=1, backoff_seconds=(1.0,)),
        rate_limiter=ProviderRateLimiter("fmp", max_requests_per_minute=1, reserve_ratio=0.0),
    )

    first = client.get_cash_flow_statements("AAPL", period="annual", limit=1)
    assert first[0]["date"] == "2025-12-31"

    with pytest.raises(ProviderQuotaExceededError):
        client.get_cash_flow_statements("AAPL", period="annual", limit=1)
