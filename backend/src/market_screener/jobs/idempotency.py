"""Helpers for deterministic ingestion idempotency keys."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def build_idempotency_key(job_name: str, dimensions: Mapping[str, Any]) -> str:
    """Build deterministic idempotency key from a stable JSON payload."""

    payload = {
        "job_name": job_name,
        "dimensions": _normalize_mapping(dimensions),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{job_name}:{digest[:40]}"


def file_sha256(path: Path) -> str:
    """Compute hex SHA256 for file bytes."""

    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _normalize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            normalized[key] = _normalize_mapping(item)
        elif isinstance(item, (list, tuple)):
            normalized[key] = [_normalize_item(entry) for entry in item]
        else:
            normalized[key] = _normalize_item(item)
    return normalized


def _normalize_item(item: Any) -> Any:
    if item is None or isinstance(item, (str, int, float, bool)):
        return item
    return str(item)
