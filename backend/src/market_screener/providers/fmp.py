"""FinancialModelingPrep (FMP) provider wrapper for fundamentals data."""

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


class FMPFundamentalsClient:
    """Thin client wrapper for FMP fundamentals endpoints."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://financialmodelingprep.com/api/v3",
        connect_timeout_seconds: int = 5,
        read_timeout_seconds: int = 12,
        total_timeout_seconds: int = 15,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: ProviderRateLimiter | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ProviderConfigError("fmp_api_key is required")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._retry_policy = retry_policy or RetryPolicy(
            attempts=3, backoff_seconds=(1.0, 2.0, 4.0)
        )
        self._rate_limiter = rate_limiter or ProviderRateLimiter(
            "fmp",
            max_requests_per_minute=60,
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
    def from_settings(cls, settings: Settings) -> "FMPFundamentalsClient":
        """Construct client using global runtime settings."""

        return cls(
            api_key=settings.fmp_api_key or "",
            connect_timeout_seconds=settings.http_connect_timeout_seconds,
            read_timeout_seconds=settings.http_read_timeout_seconds,
            total_timeout_seconds=settings.http_total_timeout_seconds,
            retry_policy=RetryPolicy.from_settings(
                attempts=settings.http_retry_attempts,
                backoff_csv=settings.http_backoff_seconds,
            ),
            rate_limiter=ProviderRateLimiter(
                "fmp",
                max_requests_per_minute=settings.fmp_quota_per_minute,
                reserve_ratio=settings.provider_quota_reserve_ratio,
            ),
        )

    def close(self) -> None:
        """Close owned HTTP client resources."""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "FMPFundamentalsClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def get_income_statements(
        self,
        symbol: str,
        *,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch income statement entries."""

        return self._fetch_list(
            f"/income-statement/{symbol}",
            params={"period": period, "limit": limit},
            schema_error="fmp_income_statement_payload_must_be_array_of_objects",
        )

    def get_balance_sheet_statements(
        self,
        symbol: str,
        *,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch balance sheet entries."""

        return self._fetch_list(
            f"/balance-sheet-statement/{symbol}",
            params={"period": period, "limit": limit},
            schema_error="fmp_balance_sheet_payload_must_be_array_of_objects",
        )

    def get_cash_flow_statements(
        self,
        symbol: str,
        *,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch cash-flow statement entries."""

        return self._fetch_list(
            f"/cash-flow-statement/{symbol}",
            params={"period": period, "limit": limit},
            schema_error="fmp_cash_flow_payload_must_be_array_of_objects",
        )

    def get_key_metrics(
        self,
        symbol: str,
        *,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch key-metrics entries."""

        return self._fetch_list(
            f"/key-metrics/{symbol}",
            params={"period": period, "limit": limit},
            schema_error="fmp_key_metrics_payload_must_be_array_of_objects",
        )

    def quota_snapshot(self) -> dict[str, float | int | str]:
        """Return current quota counters for observability."""

        return self._rate_limiter.snapshot()

    def _fetch_list(
        self,
        path: str,
        *,
        params: Mapping[str, str | int | float] | None,
        schema_error: str,
    ) -> list[dict[str, Any]]:
        payload = self._request(path, params=params)
        if not isinstance(payload, list):
            raise ProviderSchemaError(schema_error)
        if not all(isinstance(item, dict) for item in payload):
            raise ProviderSchemaError(schema_error)
        return payload

    def _request(
        self,
        path: str,
        *,
        params: Mapping[str, str | int | float] | None = None,
    ) -> Any:
        query_params: dict[str, str | int | float] = {"apikey": self.api_key}
        if params:
            query_params.update(params)

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
                raise ProviderRateLimitError("fmp_rate_limited_http_429")
            response.raise_for_status()
        except ProviderRateLimitError:
            raise
        except httpx.HTTPStatusError as exc:
            raise ProviderRequestError(f"fmp_http_error status={exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError(f"fmp_request_failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaError("fmp_non_json_response") from exc

        if isinstance(payload, dict):
            if payload.get("Error Message"):
                raise ProviderResponseError(str(payload["Error Message"]))
            if payload.get("error"):
                message = str(payload["error"])
                if "limit" in message.lower() or "rate" in message.lower():
                    raise ProviderRateLimitError(message)
                raise ProviderResponseError(message)
        elif not isinstance(payload, list):
            raise ProviderSchemaError("fmp_payload_must_be_dict_or_list")

        return payload

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
