"""Breakout detection logic based on recent price structure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BreakoutInput:
    """Input feature set required for breakout detection."""

    ts: datetime
    close: float
    high: float
    low: float
    recent_high: float | None
    recent_low: float | None
    bb_upper: float | None = None
    bb_lower: float | None = None
    atr14: float | None = None


@dataclass(frozen=True)
class BreakoutDecision:
    """Breakout detection result for one timestamp."""

    ts: datetime
    signal: str
    confidence: float
    reasons: list[str]


VALID_BREAKOUT_SIGNALS = {
    "upside_breakout",
    "downside_breakout",
    "none",
    "unknown",
}


def detect_breakout(
    point: BreakoutInput,
    *,
    breakout_buffer_ratio: float = 0.002,
) -> BreakoutDecision:
    """Detect breakout or breakdown from recent structure."""

    if point.recent_high is None or point.recent_low is None:
        return BreakoutDecision(
            ts=point.ts,
            signal="unknown",
            confidence=0.0,
            reasons=["missing_recent_range"],
        )
    if point.recent_high <= 0 or point.recent_low <= 0 or point.recent_high <= point.recent_low:
        return BreakoutDecision(
            ts=point.ts,
            signal="unknown",
            confidence=0.0,
            reasons=["invalid_recent_range"],
        )

    buffer_ratio = max(0.0, breakout_buffer_ratio)
    upper_trigger = point.recent_high * (1.0 + buffer_ratio)
    lower_trigger = point.recent_low * (1.0 - buffer_ratio)

    upside_hit = point.close >= upper_trigger or point.high >= upper_trigger
    downside_hit = point.close <= lower_trigger or point.low <= lower_trigger

    if upside_hit and not downside_hit:
        reasons = ["close_or_high_above_recent_high"]
        confidence = 0.78
        if point.bb_upper is not None and point.close >= point.bb_upper:
            reasons.append("close_above_bb_upper")
            confidence = 0.86
        if point.atr14 is not None and point.close > 0 and (point.atr14 / point.close) >= 0.03:
            reasons.append("atr_expansion")
            confidence = min(0.92, confidence + 0.04)
        return BreakoutDecision(
            ts=point.ts,
            signal="upside_breakout",
            confidence=confidence,
            reasons=reasons,
        )

    if downside_hit and not upside_hit:
        reasons = ["close_or_low_below_recent_low"]
        confidence = 0.78
        if point.bb_lower is not None and point.close <= point.bb_lower:
            reasons.append("close_below_bb_lower")
            confidence = 0.86
        if point.atr14 is not None and point.close > 0 and (point.atr14 / point.close) >= 0.03:
            reasons.append("atr_expansion")
            confidence = min(0.92, confidence + 0.04)
        return BreakoutDecision(
            ts=point.ts,
            signal="downside_breakout",
            confidence=confidence,
            reasons=reasons,
        )

    if upside_hit and downside_hit:
        return BreakoutDecision(
            ts=point.ts,
            signal="unknown",
            confidence=0.25,
            reasons=["outside_range_both_sides"],
        )

    return BreakoutDecision(
        ts=point.ts,
        signal="none",
        confidence=0.70,
        reasons=["within_recent_range"],
    )


def detect_breakout_series(
    points: list[BreakoutInput],
    *,
    breakout_buffer_ratio: float = 0.002,
) -> list[BreakoutDecision]:
    """Detect breakouts across a series sorted by timestamp."""

    return [
        detect_breakout(point, breakout_buffer_ratio=breakout_buffer_ratio)
        for point in sorted(points, key=lambda item: item.ts)
    ]
