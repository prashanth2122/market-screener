"""CoinGecko provider wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from market_screener.core.settings import Settings
from market_screener.providers.exceptions import (
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderSchemaError,
)
from market_screener.providers.rate_limit import ProviderRateLimiter
from market_screener.providers.retry import RetryPolicy, request_with_retry


class CoinGeckoClient:
    """Thin client wrapper for CoinGecko crypto market-data endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.coingecko.com/api/v3",
        connect_timeout_seconds: int = 5,
        read_timeout_seconds: int = 12,
        total_timeout_seconds: int = 15,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: ProviderRateLimiter | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self._retry_policy = retry_policy or RetryPolicy(
            attempts=3, backoff_seconds=(1.0, 2.0, 4.0)
        )
        self._rate_limiter = rate_limiter or ProviderRateLimiter(
            "coingecko",
            max_requests_per_minute=30,
            reserve_ratio=0.1,
        )
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                timeout=total_timeout_seconds,
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
            ),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "CoinGeckoClient":
        """Construct client using global runtime settings."""

        return cls(
            api_key=settings.coingecko_api_key,
            connect_timeout_seconds=settings.http_connect_timeout_seconds,
            read_timeout_seconds=settings.http_read_timeout_seconds,
            total_timeout_seconds=settings.http_total_timeout_seconds,
            retry_policy=RetryPolicy.from_settings(
                attempts=settings.http_retry_attempts,
                backoff_csv=settings.http_backoff_seconds,
            ),
            rate_limiter=ProviderRateLimiter(
                "coingecko",
                max_requests_per_minute=settings.coingecko_quota_per_minute,
                reserve_ratio=settings.provider_quota_reserve_ratio,
            ),
        )

    def close(self) -> None:
        """Close owned HTTP client resources."""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "CoinGeckoClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _request(
        self,
        path: str,
        params: Mapping[str, str | int | float | bool] | None = None,
    ) -> Any:
        query_params: dict[str, str | int | float | bool] = {}
        if params:
            query_params.update(params)
        if self.api_key:
            query_params["x_cg_demo_api_key"] = self.api_key

        try:
            response = request_with_retry(
                self._client,
                "GET",
                path,
                params=query_params,
                policy=self._retry_policy,
                on_attempt_start=self._rate_limiter.acquire,
                on_attempt_result=self._record_attempt,
            )
            if response.status_code == 429:
                raise ProviderRateLimitError("coingecko_rate_limited_http_429")
            response.raise_for_status()
        except ProviderRateLimitError:
            raise
        except httpx.HTTPStatusError as exc:
            raise ProviderRequestError(
                f"coingecko_http_error status={exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError(f"coingecko_request_failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaError("coingecko_non_json_response") from exc

        if not isinstance(payload, (dict, list)):
            raise ProviderSchemaError("coingecko_payload_must_be_dict_or_list")

        if isinstance(payload, dict):
            error_message = self._extract_error_message(payload)
            if error_message:
                if "rate" in error_message.lower() or "limit" in error_message.lower():
                    raise ProviderRateLimitError(error_message)
                raise ProviderResponseError(error_message)

        return payload

    def get_simple_price(
        self,
        *,
        ids: str,
        vs_currencies: str,
        include_24hr_change: bool = True,
    ) -> dict[str, Any]:
        """Fetch spot price snapshot for one or more coin ids."""

        payload = self._request(
            "/simple/price",
            {
                "ids": ids,
                "vs_currencies": vs_currencies,
                "include_24hr_change": str(include_24hr_change).lower(),
            },
        )
        if not isinstance(payload, dict):
            raise ProviderSchemaError("coingecko_simple_price_payload_must_be_object")
        return payload

    def get_coin_markets(
        self,
        *,
        vs_currency: str,
        order: str = "market_cap_desc",
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Fetch paginated coin market summary records."""

        payload = self._request(
            "/coins/markets",
            {
                "vs_currency": vs_currency,
                "order": order,
                "per_page": per_page,
                "page": page,
            },
        )
        if not isinstance(payload, list):
            raise ProviderSchemaError("coingecko_coin_markets_payload_must_be_array")
        if not all(isinstance(item, dict) for item in payload):
            raise ProviderSchemaError("coingecko_coin_markets_items_must_be_objects")
        return payload

    def get_coin_market_chart(
        self,
        coin_id: str,
        *,
        vs_currency: str,
        days: int,
        interval: str | None = None,
    ) -> dict[str, Any]:
        """Fetch historical market chart data for a coin id."""

        query: dict[str, str | int | float | bool] = {
            "vs_currency": vs_currency,
            "days": days,
        }
        if interval:
            query["interval"] = interval

        payload = self._request(f"/coins/{coin_id}/market_chart", query)
        if not isinstance(payload, dict):
            raise ProviderSchemaError("coingecko_market_chart_payload_must_be_object")
        return payload

    def get_coin_ohlc(
        self,
        coin_id: str,
        *,
        vs_currency: str,
        days: int,
    ) -> list[list[float | int]]:
        """Fetch OHLC candles for a coin id."""

        payload = self._request(
            f"/coins/{coin_id}/ohlc",
            {
                "vs_currency": vs_currency,
                "days": days,
            },
        )
        if not isinstance(payload, list):
            raise ProviderSchemaError("coingecko_ohlc_payload_must_be_array")
        if not all(isinstance(item, list) for item in payload):
            raise ProviderSchemaError("coingecko_ohlc_items_must_be_arrays")
        return payload

    def quota_snapshot(self) -> dict[str, float | int | str]:
        """Return current quota counters for observability."""

        return self._rate_limiter.snapshot()

    def _record_attempt(
        self,
        response: httpx.Response | None,
        error: Exception | None,
        latency_ms: float,
    ) -> None:
        if error:
            self._rate_limiter.record_exception()
            return
        if response is not None:
            self._rate_limiter.record_response(response.status_code, latency_ms)

    @staticmethod
    def _extract_error_message(payload: dict[str, Any]) -> str | None:
        if isinstance(payload.get("error"), str):
            return str(payload["error"])
        status = payload.get("status")
        if isinstance(status, dict):
            if isinstance(status.get("error_message"), str):
                return str(status["error_message"])
            if isinstance(status.get("message"), str):
                return str(status["message"])
        return None
