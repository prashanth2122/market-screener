"""Marketaux provider wrapper for news article retrieval."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
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


class MarketauxNewsClient:
    """Thin client wrapper for Marketaux news endpoints."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = "https://api.marketaux.com/v1",
        connect_timeout_seconds: int = 5,
        read_timeout_seconds: int = 12,
        total_timeout_seconds: int = 15,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: ProviderRateLimiter | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_token:
            raise ProviderConfigError("marketaux_api_key is required")

        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self._retry_policy = retry_policy or RetryPolicy(
            attempts=3, backoff_seconds=(1.0, 2.0, 4.0)
        )
        self._rate_limiter = rate_limiter or ProviderRateLimiter(
            "marketaux",
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
    def from_settings(cls, settings: Settings) -> "MarketauxNewsClient":
        """Construct client using global runtime settings."""

        return cls(
            api_token=settings.marketaux_api_key or "",
            connect_timeout_seconds=settings.http_connect_timeout_seconds,
            read_timeout_seconds=settings.http_read_timeout_seconds,
            total_timeout_seconds=settings.http_total_timeout_seconds,
            retry_policy=RetryPolicy.from_settings(
                attempts=settings.http_retry_attempts,
                backoff_csv=settings.http_backoff_seconds,
            ),
            rate_limiter=ProviderRateLimiter(
                "marketaux",
                max_requests_per_minute=settings.marketaux_quota_per_minute,
                reserve_ratio=settings.provider_quota_reserve_ratio,
            ),
        )

    def close(self) -> None:
        """Close owned HTTP client resources."""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "MarketauxNewsClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def get_news(
        self,
        symbol: str,
        *,
        limit: int,
        language: str = "en",
        published_after: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch recent news articles for one symbol."""

        params: dict[str, str | int | float] = {
            "symbols": symbol,
            "limit": max(1, limit),
            "language": language,
        }
        if published_after is not None:
            normalized = published_after.astimezone(UTC).replace(microsecond=0)
            params["published_after"] = normalized.isoformat().replace("+00:00", "Z")

        payload = self._request("/news/all", params=params)
        if not isinstance(payload, dict):
            raise ProviderSchemaError("marketaux_payload_must_be_object")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderSchemaError("marketaux_news_payload_must_include_data_list")
        if not all(isinstance(item, dict) for item in data):
            raise ProviderSchemaError("marketaux_news_items_must_be_objects")
        return data

    def quota_snapshot(self) -> dict[str, float | int | str]:
        """Return current quota counters for observability."""

        return self._rate_limiter.snapshot()

    def _request(
        self,
        path: str,
        *,
        params: Mapping[str, str | int | float] | None = None,
    ) -> Any:
        query_params: dict[str, str | int | float] = {"api_token": self.api_token}
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
                raise ProviderRateLimitError("marketaux_rate_limited_http_429")
            response.raise_for_status()
        except ProviderRateLimitError:
            raise
        except httpx.HTTPStatusError as exc:
            raise ProviderRequestError(
                f"marketaux_http_error status={exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError(f"marketaux_request_failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaError("marketaux_non_json_response") from exc

        if isinstance(payload, dict) and "error" in payload:
            error_value = payload.get("error")
            if isinstance(error_value, dict):
                message = str(
                    error_value.get("message") or error_value.get("code") or "unknown_error"
                )
            else:
                message = str(error_value)
            if "limit" in message.lower() or "rate" in message.lower():
                raise ProviderRateLimitError(message)
            raise ProviderResponseError(message)

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
