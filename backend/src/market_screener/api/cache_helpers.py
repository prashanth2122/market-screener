"""Helpers for API response caching."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlencode

from fastapi import Request

from market_screener.api.response_cache import ApiResponseCache
from market_screener.core.settings import Settings  # noqa: F401


@lru_cache
def get_api_cache(*, max_entries: int) -> ApiResponseCache:
    return ApiResponseCache(max_entries=max_entries)


def build_cache_key(request: Request, *, drop_params: set[str] | None = None) -> str:
    drop = drop_params or set()
    items = [(k, v) for k, v in request.query_params.multi_items() if k not in drop]
    items.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(items, doseq=True)
    if query:
        return f"{request.url.path}?{query}"
    return request.url.path
