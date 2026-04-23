"""Tests for breakout detection logic."""

from __future__ import annotations

from datetime import UTC, datetime

from market_screener.core.breakout import (
    BreakoutInput,
    detect_breakout,
    detect_breakout_series,
)


def _point(
    *,
    day: int,
    close: float,
    high: float,
    low: float,
    recent_high: float | None,
    recent_low: float | None,
    bb_upper: float | None = None,
    bb_lower: float | None = None,
    atr14: float | None = None,
) -> BreakoutInput:
    return BreakoutInput(
        ts=datetime(2026, 4, day, tzinfo=UTC),
        close=close,
        high=high,
        low=low,
        recent_high=recent_high,
        recent_low=recent_low,
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        atr14=atr14,
    )


def test_detect_breakout_upside() -> None:
    decision = detect_breakout(
        _point(
            day=21,
            close=103.0,
            high=103.5,
            low=101.0,
            recent_high=100.0,
            recent_low=95.0,
            bb_upper=102.0,
            atr14=4.0,
        ),
        breakout_buffer_ratio=0.002,
    )

    assert decision.signal == "upside_breakout"
    assert decision.confidence >= 0.86
    assert "close_above_bb_upper" in decision.reasons


def test_detect_breakout_downside() -> None:
    decision = detect_breakout(
        _point(
            day=21,
            close=92.0,
            high=94.0,
            low=91.5,
            recent_high=105.0,
            recent_low=95.0,
            bb_lower=93.0,
            atr14=3.0,
        ),
        breakout_buffer_ratio=0.002,
    )

    assert decision.signal == "downside_breakout"
    assert decision.confidence >= 0.86
    assert "close_below_bb_lower" in decision.reasons


def test_detect_breakout_none_within_range() -> None:
    decision = detect_breakout(
        _point(
            day=21,
            close=99.0,
            high=100.0,
            low=98.0,
            recent_high=101.0,
            recent_low=97.0,
        ),
        breakout_buffer_ratio=0.002,
    )

    assert decision.signal == "none"
    assert decision.reasons == ["within_recent_range"]


def test_detect_breakout_unknown_when_range_missing() -> None:
    decision = detect_breakout(
        _point(
            day=21,
            close=99.0,
            high=100.0,
            low=98.0,
            recent_high=None,
            recent_low=97.0,
        )
    )

    assert decision.signal == "unknown"
    assert decision.reasons == ["missing_recent_range"]


def test_detect_breakout_series_sorts_by_timestamp() -> None:
    points = [
        _point(
            day=23,
            close=103.0,
            high=103.0,
            low=102.0,
            recent_high=100.0,
            recent_low=95.0,
        ),
        _point(
            day=21,
            close=99.0,
            high=100.0,
            low=98.0,
            recent_high=101.0,
            recent_low=97.0,
        ),
        _point(
            day=22,
            close=92.0,
            high=94.0,
            low=91.0,
            recent_high=105.0,
            recent_low=95.0,
        ),
    ]

    decisions = detect_breakout_series(points, breakout_buffer_ratio=0.002)

    assert [decision.ts.day for decision in decisions] == [21, 22, 23]
    assert [decision.signal for decision in decisions] == [
        "none",
        "downside_breakout",
        "upside_breakout",
    ]
