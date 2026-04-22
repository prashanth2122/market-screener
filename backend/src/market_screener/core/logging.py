"""Structured logging setup for backend services."""

from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone
from typing import Any

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_base_record_fields = set(logging.LogRecord("", logging.INFO, "", 0, "", (), None).__dict__.keys())


class RequestContextFilter(logging.Filter):
    """Inject request context values into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.request_id = _request_id_ctx.get()
        return True


class StructuredJsonFormatter(logging.Formatter):
    """Render log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }

        for key, value in record.__dict__.items():
            if key in _base_record_fields or key in {"message", "asctime"}:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, separators=(",", ":"))


def set_request_id(request_id: str) -> contextvars.Token[str]:
    """Set request ID for current context and return reset token."""

    return _request_id_ctx.set(request_id)


def reset_request_id(token: contextvars.Token[str]) -> None:
    """Reset request ID context using the token returned by `set_request_id`."""

    _request_id_ctx.reset(token)


def configure_logging(level: str = "INFO", log_json: bool = True) -> None:
    """Configure process-wide logging handlers and format."""

    resolved_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    if log_json:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s"
            )
        )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(resolved_level)
    root_logger.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
