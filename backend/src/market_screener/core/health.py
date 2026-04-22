"""Runtime health checks for core dependencies."""

from __future__ import annotations

import socket
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from market_screener.core.settings import Settings


def check_postgres(database_url: str, timeout_seconds: int = 3) -> dict[str, Any]:
    """Probe PostgreSQL connectivity with a lightweight query."""

    started = time.perf_counter()
    try:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": timeout_seconds},
        )
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except (SQLAlchemyError, OSError) as exc:
        return {
            "status": "down",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }

    return {
        "status": "up",
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "error": None,
    }


def check_redis(redis_url: str, timeout_seconds: float = 2.0) -> dict[str, Any]:
    """Probe Redis by opening a TCP connection to the configured host/port."""

    parts = urlsplit(redis_url)
    host = parts.hostname or "localhost"
    port = parts.port or 6379
    started = time.perf_counter()

    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass
    except OSError as exc:
        return {
            "status": "down",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }

    return {
        "status": "up",
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "error": None,
    }


def evaluate_runtime_health(settings: Settings) -> dict[str, Any]:
    """Evaluate application and dependency health status."""

    db_check = check_postgres(settings.sqlalchemy_database_url)
    redis_check = check_redis(settings.redis_url or "")
    overall_status = (
        "ok" if db_check["status"] == "up" and redis_check["status"] == "up" else "degraded"
    )

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "database": db_check,
            "redis": redis_check,
        },
    }
