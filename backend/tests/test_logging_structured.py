"""Tests for structured logging behavior."""

from __future__ import annotations

import json
import logging

from market_screener.core.logging import (
    RequestContextFilter,
    StructuredJsonFormatter,
    reset_request_id,
    set_request_id,
)


def test_structured_formatter_outputs_json_with_extra_fields() -> None:
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="market_screener.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello_world",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.symbol = "AAPL"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello_world"
    assert payload["logger"] == "market_screener.test"
    assert payload["request_id"] == "req-123"
    assert payload["symbol"] == "AAPL"


def test_request_context_filter_injects_context_request_id() -> None:
    token = set_request_id("req-ctx-001")
    try:
        record = logging.LogRecord(
            name="market_screener.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=20,
            msg="context_test",
            args=(),
            exc_info=None,
        )
        assert RequestContextFilter().filter(record) is True
        assert getattr(record, "request_id") == "req-ctx-001"
    finally:
        reset_request_id(token)
