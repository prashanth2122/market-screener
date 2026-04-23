"""System-level routes used for smoke and uptime checks."""

from typing import Any

from fastapi import APIRouter
from fastapi import Depends, Response, status

from market_screener.core.health import evaluate_runtime_health
from market_screener.core.settings import Settings, get_settings
from market_screener.db.session import create_session_factory_from_settings
from market_screener.jobs.provider_health_dashboard import (
    read_provider_health_dashboard,
    run_provider_health_dashboard,
)

router = APIRouter(tags=["system"])


@router.get("/ping")
def ping() -> dict[str, str]:
    """Simple ping endpoint to verify service responsiveness."""

    return {"status": "ok"}


@router.get("/health")
def health(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Dependency-aware health endpoint for readiness checks."""

    payload = evaluate_runtime_health(settings)
    if payload["status"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


@router.get("/provider-health")
def provider_health(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Read provider latency/success dashboard data."""

    session_factory = create_session_factory_from_settings(settings)
    return read_provider_health_dashboard(
        session_factory,
        lookback_hours=settings.provider_health_lookback_hours,
        history_limit=settings.provider_health_dashboard_history_limit,
    )


@router.post("/provider-health/refresh")
def refresh_provider_health(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Refresh provider latency/success snapshots from recent job runs."""

    session_factory = create_session_factory_from_settings(settings)
    result = run_provider_health_dashboard(
        settings=settings,
        session_factory=session_factory,
    )
    return {
        "status": "ok",
        "provider_count": result.provider_count,
        "providers": [snapshot.provider_name for snapshot in result.providers],
        "lookback_hours": result.lookback_hours,
        "sample_limit": result.sample_limit,
    }
