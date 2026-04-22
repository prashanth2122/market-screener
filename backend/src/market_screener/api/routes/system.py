"""System-level routes used for smoke and uptime checks."""

from typing import Any

from fastapi import APIRouter
from fastapi import Depends, Response, status

from market_screener.core.health import evaluate_runtime_health
from market_screener.core.settings import Settings, get_settings

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
