"""Tests for Alpha Vantage provider wrapper."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from market_screener.providers.alpha_vantage import AlphaVantageClient
from market_screener.providers.exceptions import (
    ProviderConfigError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderSchemaError,
)


def _build_client(handler: Callable[[httpx.Request], httpx.Response]) -> AlphaVantageClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://www.alphavantage.co/query",
        timeout=httpx.Timeout(timeout=15, connect=5, read=12),
    )
    return AlphaVantageClient(api_key="demo-key", client=http_client)


def test_global_quote_builds_required_query_params() -> None:
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json={"Global Quote": {"01. symbol": "IBM"}})

    client = _build_client(handler)

    payload = client.get_global_quote("IBM")

    assert payload["Global Quote"]["01. symbol"] == "IBM"
    assert captured_params["function"] == "GLOBAL_QUOTE"
    assert captured_params["symbol"] == "IBM"
    assert captured_params["apikey"] == "demo-key"


def test_daily_time_series_uses_adjusted_function_by_default() -> None:
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json={"Meta Data": {"2. Symbol": "AAPL"}})

    client = _build_client(handler)

    client.get_daily_time_series("AAPL")

    assert captured_params["function"] == "TIME_SERIES_DAILY_ADJUSTED"
    assert captured_params["outputsize"] == "compact"


def test_raises_rate_limit_error_for_note_payload() -> None:
    client = _build_client(
        lambda _request: httpx.Response(200, json={"Note": "Thank you for using Alpha Vantage!"})
    )

    with pytest.raises(ProviderRateLimitError):
        client.get_global_quote("IBM")


def test_raises_provider_response_error_for_error_message_payload() -> None:
    client = _build_client(
        lambda _request: httpx.Response(200, json={"Error Message": "Invalid API call."})
    )

    with pytest.raises(ProviderResponseError):
        client.get_global_quote("IBM")


def test_raises_schema_error_for_non_json_response() -> None:
    client = _build_client(
        lambda _request: httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            content=b"not-json",
        )
    )

    with pytest.raises(ProviderSchemaError):
        client.get_global_quote("IBM")


def test_missing_api_key_raises_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        AlphaVantageClient(api_key="")
