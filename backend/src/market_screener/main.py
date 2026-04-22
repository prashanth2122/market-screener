"""FastAPI application entrypoint."""

import logging
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, Response, status

from market_screener.api.router import api_router
from market_screener.core.health import evaluate_runtime_health
from market_screener.core.logging import configure_logging, reset_request_id, set_request_id
from market_screener.core.settings import Settings, get_settings

request_logger = logging.getLogger("market_screener.request")


def create_app() -> FastAPI:
    """Application factory for tests and runtime."""

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    application = FastAPI(
        title=f"{settings.app_name}-backend",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        token = set_request_id(request_id)
        started = time.perf_counter()

        request_logger.info(
            "request_started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
            },
        )

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            request_logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise
        else:
            duration_ms = int((time.perf_counter() - started) * 1000)
            response.headers["X-Request-ID"] = request_id
            request_logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            reset_request_id(token)

    @application.get("/")
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "status": "bootstrapped"}

    @application.get("/health")
    def health(
        response: Response,
        runtime_settings: Settings = Depends(get_settings),
    ) -> dict[str, object]:
        payload = evaluate_runtime_health(runtime_settings)
        if payload["status"] != "ok":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return payload

    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
