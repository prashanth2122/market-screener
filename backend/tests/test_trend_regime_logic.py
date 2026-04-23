"""Tests for trend regime classification logic."""

from __future__ import annotations

from datetime import UTC, datetime

from market_screener.core.trend_regime import (
    classify_trend_regime,
    classify_trend_regime_series,
    TrendRegimeInput,
)


def _point(
    *,
    ts_day: int,
    ma50: float | None,
    ma200: float | None,
    rsi14: float | None,
    macd: float | None,
    macd_signal: float | None,
) -> TrendRegimeInput:
    return TrendRegimeInput(
        ts=datetime(2026, 4, ts_day, tzinfo=UTC),
        ma50=ma50,
        ma200=ma200,
        rsi14=rsi14,
        macd=macd,
        macd_signal=macd_signal,
        atr14=2.0,
        bb_upper=110.0,
        bb_lower=100.0,
    )


def test_classify_trend_regime_bullish() -> None:
    decision = classify_trend_regime(
        _point(ts_day=21, ma50=105.0, ma200=100.0, rsi14=60.0, macd=1.2, macd_signal=0.8)
    )

    assert decision.regime == "bullish"
    assert decision.confidence >= 0.8
    assert "ma50_above_ma200" in decision.reasons


def test_classify_trend_regime_bearish() -> None:
    decision = classify_trend_regime(
        _point(ts_day=21, ma50=95.0, ma200=100.0, rsi14=40.0, macd=-1.0, macd_signal=-0.5)
    )

    assert decision.regime == "bearish"
    assert decision.confidence >= 0.8
    assert "ma50_below_ma200" in decision.reasons


def test_classify_trend_regime_accumulation() -> None:
    decision = classify_trend_regime(
        _point(ts_day=21, ma50=95.0, ma200=100.0, rsi14=52.0, macd=0.4, macd_signal=0.2)
    )

    assert decision.regime == "accumulation"
    assert "macd_reversal_signal" in decision.reasons


def test_classify_trend_regime_distribution() -> None:
    decision = classify_trend_regime(
        _point(ts_day=21, ma50=105.0, ma200=100.0, rsi14=48.0, macd=-0.3, macd_signal=-0.2)
    )

    assert decision.regime == "distribution"
    assert "macd_reversal_signal" in decision.reasons


def test_classify_trend_regime_range() -> None:
    decision = classify_trend_regime(
        _point(ts_day=21, ma50=100.0, ma200=100.0, rsi14=50.0, macd=0.03, macd_signal=0.00),
        macd_flat_tolerance=0.05,
    )

    assert decision.regime == "range"
    assert "flat_macd" in decision.reasons


def test_classify_trend_regime_unknown_when_moving_average_missing() -> None:
    decision = classify_trend_regime(
        _point(ts_day=21, ma50=None, ma200=100.0, rsi14=55.0, macd=0.4, macd_signal=0.1)
    )

    assert decision.regime == "unknown"
    assert decision.confidence == 0.0
    assert decision.reasons == ["missing_moving_average_context"]


def test_classify_trend_regime_series_sorts_by_timestamp() -> None:
    points = [
        _point(ts_day=23, ma50=105.0, ma200=100.0, rsi14=59.0, macd=0.8, macd_signal=0.2),
        _point(ts_day=21, ma50=95.0, ma200=100.0, rsi14=41.0, macd=-0.5, macd_signal=-0.2),
        _point(ts_day=22, ma50=100.0, ma200=100.0, rsi14=50.0, macd=0.02, macd_signal=0.0),
    ]

    decisions = classify_trend_regime_series(points, macd_flat_tolerance=0.05)

    assert [decision.ts.day for decision in decisions] == [21, 22, 23]
    assert [decision.regime for decision in decisions] == ["bearish", "range", "bullish"]
