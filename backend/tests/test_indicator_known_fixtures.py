"""Fixture-driven indicator unit tests with known expected outputs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from market_screener.core.breakout import BreakoutInput, detect_breakout
from market_screener.core.relative_volume import (
    RelativeVolumeInput,
    calculate_relative_volume,
)
from market_screener.core.trend_regime import TrendRegimeInput, classify_trend_regime

FIXTURE_FILE = Path(__file__).parent / "fixtures" / "indicator_known_fixtures.json"
KNOWN_FIXTURES = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "case",
    KNOWN_FIXTURES["trend_regime"],
    ids=[item["name"] for item in KNOWN_FIXTURES["trend_regime"]],
)
def test_trend_regime_known_fixtures(case: dict[str, Any]) -> None:
    payload = case["input"]
    decision = classify_trend_regime(
        TrendRegimeInput(
            ts=datetime.fromisoformat(payload["ts"]),
            ma50=payload.get("ma50"),
            ma200=payload.get("ma200"),
            rsi14=payload.get("rsi14"),
            macd=payload.get("macd"),
            macd_signal=payload.get("macd_signal"),
            atr14=payload.get("atr14"),
            bb_upper=payload.get("bb_upper"),
            bb_lower=payload.get("bb_lower"),
        ),
        **case.get("params", {}),
    )
    expected = case["expected"]
    assert decision.regime == expected["regime"]
    if "confidence_min" in expected:
        assert decision.confidence >= expected["confidence_min"]
    if "confidence_exact" in expected:
        assert decision.confidence == expected["confidence_exact"]
    for reason in expected.get("reasons_contains", []):
        assert reason in decision.reasons


@pytest.mark.parametrize(
    "case",
    KNOWN_FIXTURES["breakout"],
    ids=[item["name"] for item in KNOWN_FIXTURES["breakout"]],
)
def test_breakout_known_fixtures(case: dict[str, Any]) -> None:
    payload = case["input"]
    decision = detect_breakout(
        BreakoutInput(
            ts=datetime.fromisoformat(payload["ts"]),
            close=payload["close"],
            high=payload["high"],
            low=payload["low"],
            recent_high=payload.get("recent_high"),
            recent_low=payload.get("recent_low"),
            bb_upper=payload.get("bb_upper"),
            bb_lower=payload.get("bb_lower"),
            atr14=payload.get("atr14"),
        ),
        **case.get("params", {}),
    )
    expected = case["expected"]
    assert decision.signal == expected["signal"]
    if "confidence_min" in expected:
        assert decision.confidence >= expected["confidence_min"]
    if "confidence_exact" in expected:
        assert decision.confidence == expected["confidence_exact"]
    for reason in expected.get("reasons_contains", []):
        assert reason in decision.reasons


@pytest.mark.parametrize(
    "case",
    KNOWN_FIXTURES["relative_volume"],
    ids=[item["name"] for item in KNOWN_FIXTURES["relative_volume"]],
)
def test_relative_volume_known_fixtures(case: dict[str, Any]) -> None:
    payload = case["input"]
    decision = calculate_relative_volume(
        RelativeVolumeInput(
            ts=datetime.fromisoformat(payload["ts"]),
            current_volume=payload.get("current_volume"),
            baseline_volumes=payload["baseline_volumes"],
        ),
        **case.get("params", {}),
    )
    expected = case["expected"]
    assert decision.state == expected["state"]
    if "ratio_min" in expected:
        assert decision.ratio is not None
        assert decision.ratio >= expected["ratio_min"]
    if "ratio_max" in expected:
        assert decision.ratio is not None
        assert decision.ratio <= expected["ratio_max"]
    if expected.get("ratio_null"):
        assert decision.ratio is None
    for reason in expected.get("reasons_contains", []):
        assert reason in decision.reasons
