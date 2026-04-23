"""Trend regime classification logic derived from indicator snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TrendRegimeInput:
    """Input feature set used to classify a trend regime."""

    ts: datetime
    ma50: float | None
    ma200: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    atr14: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None


@dataclass(frozen=True)
class TrendRegimeDecision:
    """Classification decision for one timestamp."""

    ts: datetime
    regime: str
    confidence: float
    reasons: list[str]


VALID_REGIMES = {
    "bullish",
    "bearish",
    "accumulation",
    "distribution",
    "range",
    "unknown",
}


def classify_trend_regime(
    point: TrendRegimeInput,
    *,
    macd_flat_tolerance: float = 0.10,
) -> TrendRegimeDecision:
    """Classify trend regime from indicator values."""

    if point.ma50 is None or point.ma200 is None:
        return TrendRegimeDecision(
            ts=point.ts,
            regime="unknown",
            confidence=0.0,
            reasons=["missing_moving_average_context"],
        )

    trend_up = point.ma50 >= point.ma200
    trend_down = point.ma50 < point.ma200
    macd_up = (
        point.macd is not None and point.macd_signal is not None and point.macd > point.macd_signal
    )
    macd_down = (
        point.macd is not None and point.macd_signal is not None and point.macd < point.macd_signal
    )
    macd_diff = (
        (point.macd - point.macd_signal)
        if point.macd is not None and point.macd_signal is not None
        else None
    )
    ma_spread_ratio = (
        abs(point.ma50 - point.ma200) / abs(point.ma200) if point.ma200 not in (None, 0) else None
    )
    rsi_mid = point.rsi14 is not None and 45.0 <= point.rsi14 <= 55.0
    rsi_bullish = point.rsi14 is not None and point.rsi14 >= 55.0
    rsi_bearish = point.rsi14 is not None and point.rsi14 <= 45.0

    if (
        ma_spread_ratio is not None
        and ma_spread_ratio <= 0.01
        and macd_diff is not None
        and abs(macd_diff) <= macd_flat_tolerance
        and rsi_mid
    ):
        return TrendRegimeDecision(
            ts=point.ts,
            regime="range",
            confidence=0.72,
            reasons=["flat_macd", "midline_rsi"],
        )

    if trend_up and macd_up and (point.rsi14 is None or point.rsi14 >= 50.0):
        reasons = ["ma50_above_ma200", "macd_above_signal"]
        confidence = 0.80
        if rsi_bullish:
            reasons.append("rsi_supports_uptrend")
            confidence = 0.90
        return TrendRegimeDecision(
            ts=point.ts,
            regime="bullish",
            confidence=confidence,
            reasons=_extend_with_volatility_context(point, reasons),
        )

    if trend_down and macd_down and (point.rsi14 is None or point.rsi14 <= 50.0):
        reasons = ["ma50_below_ma200", "macd_below_signal"]
        confidence = 0.80
        if rsi_bearish:
            reasons.append("rsi_confirms_weakness")
            confidence = 0.90
        return TrendRegimeDecision(
            ts=point.ts,
            regime="bearish",
            confidence=confidence,
            reasons=_extend_with_volatility_context(point, reasons),
        )

    if trend_down and macd_up:
        return TrendRegimeDecision(
            ts=point.ts,
            regime="accumulation",
            confidence=0.68,
            reasons=_extend_with_volatility_context(
                point,
                ["ma50_below_ma200", "macd_reversal_signal"],
            ),
        )

    if trend_up and macd_down:
        return TrendRegimeDecision(
            ts=point.ts,
            regime="distribution",
            confidence=0.68,
            reasons=_extend_with_volatility_context(
                point,
                ["ma50_above_ma200", "macd_reversal_signal"],
            ),
        )

    return TrendRegimeDecision(
        ts=point.ts,
        regime="unknown",
        confidence=0.30,
        reasons=_extend_with_volatility_context(point, ["mixed_indicator_state"]),
    )


def classify_trend_regime_series(
    points: list[TrendRegimeInput],
    *,
    macd_flat_tolerance: float = 0.10,
) -> list[TrendRegimeDecision]:
    """Classify a series of indicator points into trend regimes."""

    return [
        classify_trend_regime(point, macd_flat_tolerance=macd_flat_tolerance)
        for point in sorted(points, key=lambda item: item.ts)
    ]


def _extend_with_volatility_context(
    point: TrendRegimeInput,
    reasons: list[str],
) -> list[str]:
    extended = list(reasons)
    if point.ma50 is not None and point.atr14 is not None and point.ma50 != 0:
        atr_ratio = abs(point.atr14 / point.ma50)
        if atr_ratio >= 0.05:
            extended.append("high_atr_volatility")
    if (
        point.ma50 is not None
        and point.bb_upper is not None
        and point.bb_lower is not None
        and point.ma50 != 0
    ):
        band_width_ratio = abs((point.bb_upper - point.bb_lower) / point.ma50)
        if band_width_ratio <= 0.03:
            extended.append("tight_bands")
    return extended
