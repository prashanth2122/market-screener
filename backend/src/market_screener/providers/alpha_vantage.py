"""Alpha Vantage provider wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from market_screener.core.settings import Settings
from market_screener.providers.exceptions import (
    ProviderConfigError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderSchemaError,
)
from market_screener.providers.rate_limit import ProviderRateLimiter
from market_screener.providers.retry import RetryPolicy, request_with_retry


class AlphaVantageClient:
    """Thin client wrapper for Alpha Vantage market-data endpoints."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://www.alphavantage.co/query",
        connect_timeout_seconds: int = 5,
        read_timeout_seconds: int = 12,
        total_timeout_seconds: int = 15,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: ProviderRateLimiter | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ProviderConfigError("alpha_vantage_api_key is required")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._retry_policy = retry_policy or RetryPolicy(
            attempts=3, backoff_seconds=(1.0, 2.0, 4.0)
        )
        self._rate_limiter = rate_limiter or ProviderRateLimiter(
            "alpha_vantage",
            max_requests_per_minute=5,
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
    def from_settings(cls, settings: Settings) -> "AlphaVantageClient":
        """Construct client using global runtime settings."""

        return cls(
            api_key=settings.alpha_vantage_api_key or "",
            connect_timeout_seconds=settings.http_connect_timeout_seconds,
            read_timeout_seconds=settings.http_read_timeout_seconds,
            total_timeout_seconds=settings.http_total_timeout_seconds,
            retry_policy=RetryPolicy.from_settings(
                attempts=settings.http_retry_attempts,
                backoff_csv=settings.http_backoff_seconds,
            ),
            rate_limiter=ProviderRateLimiter(
                "alpha_vantage",
                max_requests_per_minute=settings.alpha_vantage_quota_per_minute,
                reserve_ratio=settings.provider_quota_reserve_ratio,
            ),
        )

    def close(self) -> None:
        """Close owned HTTP client resources."""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "AlphaVantageClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def fetch(
        self,
        function: str,
        params: Mapping[str, str | int | float] | None = None,
    ) -> dict[str, Any]:
        """Fetch a raw Alpha Vantage JSON payload for a function."""

        query_params: dict[str, str | int | float] = {
            "function": function,
            "apikey": self.api_key,
        }
        if params:
            query_params.update(params)

        try:
            response = request_with_retry(
                self._client,
                "GET",
                "",
                params=query_params,
                policy=self._retry_policy,
                on_attempt_start=self._rate_limiter.acquire,
                on_attempt_result=self._record_attempt,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderRequestError(
                f"alpha_vantage_http_error status={exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError(f"alpha_vantage_request_failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaError("alpha_vantage_non_json_response") from exc

        if not isinstance(payload, dict):
            raise ProviderSchemaError("alpha_vantage_payload_must_be_object")

        if "Note" in payload:
            raise ProviderRateLimitError(str(payload["Note"]))

        if "Information" in payload and "call frequency" in str(payload["Information"]).lower():
            raise ProviderRateLimitError(str(payload["Information"]))

        if "Error Message" in payload:
            raise ProviderResponseError(str(payload["Error Message"]))

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

    def get_global_quote(self, symbol: str) -> dict[str, Any]:
        """Fetch quote snapshot for an instrument symbol."""

        return self.fetch("GLOBAL_QUOTE", {"symbol": symbol})

    def get_daily_time_series(
        self,
        symbol: str,
        *,
        adjusted: bool = True,
        outputsize: str = "compact",
    ) -> dict[str, Any]:
        """Fetch daily OHLCV series for an equity symbol."""

        function = "TIME_SERIES_DAILY_ADJUSTED" if adjusted else "TIME_SERIES_DAILY"
        return self.fetch(function, {"symbol": symbol, "outputsize": outputsize})

    def get_fx_daily(
        self,
        from_symbol: str,
        to_symbol: str,
        *,
        outputsize: str = "compact",
    ) -> dict[str, Any]:
        """Fetch daily forex candles."""

        return self.fetch(
            "FX_DAILY",
            {
                "from_symbol": from_symbol,
                "to_symbol": to_symbol,
                "outputsize": outputsize,
            },
        )
