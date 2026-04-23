"""Tests for signal mapping rules."""

from __future__ import annotations

from datetime import UTC, datetime

from market_screener.core.composite_score import CompositeScoreInputs, compute_composite_score
from market_screener.core.score_explanation import build_score_explanation_payload
from market_screener.core.score_factors import SentimentRiskFactorInputs, TechnicalFactorInputs
from market_screener.core.signal_mapping import (
    SignalMappingInput,
    map_signal,
    map_signal_from_score_explanation,
)


def test_map_signal_returns_strong_buy_for_high_score_without_risk() -> None:
    result = map_signal(
        SignalMappingInput(
            asset_symbol="AAPL",
            score=84.0,
            confidence=0.90,
            technical_score=82.0,
            fundamental_score=75.0,
            sentiment_risk_score=62.0,
            risk_flag=False,
            event_type=None,
            unavailable_components=[],
        )
    )

    assert result.signal == "strong_buy"
    assert result.label == "Strong Buy"
    assert result.blocked_by_risk is False


def test_map_signal_returns_buy_for_constructive_score() -> None:
    result = map_signal(
        SignalMappingInput(
            asset_symbol="MSFT",
            score=72.0,
            confidence=0.82,
            technical_score=70.0,
            fundamental_score=74.0,
            sentiment_risk_score=56.0,
            risk_flag=False,
            event_type=None,
            unavailable_components=[],
        )
    )

    assert result.signal == "buy"


def test_map_signal_returns_watch_for_mid_score() -> None:
    result = map_signal(
        SignalMappingInput(
            asset_symbol="TSLA",
            score=58.0,
            confidence=0.70,
            technical_score=57.0,
            fundamental_score=61.0,
            sentiment_risk_score=52.0,
            risk_flag=False,
            event_type=None,
            unavailable_components=[],
        )
    )

    assert result.signal == "watch"


def test_map_signal_returns_avoid_for_low_score() -> None:
    result = map_signal(
        SignalMappingInput(
            asset_symbol="XYZ",
            score=42.0,
            confidence=0.78,
            technical_score=40.0,
            fundamental_score=45.0,
            sentiment_risk_score=38.0,
            risk_flag=False,
            event_type=None,
            unavailable_components=[],
        )
    )

    assert result.signal == "avoid"


def test_map_signal_enforces_severe_risk_override() -> None:
    result = map_signal(
        SignalMappingInput(
            asset_symbol="NVDA",
            score=88.0,
            confidence=0.92,
            technical_score=90.0,
            fundamental_score=82.0,
            sentiment_risk_score=70.0,
            risk_flag=True,
            event_type="fraud_or_accounting",
            unavailable_components=[],
        )
    )

    assert result.signal == "avoid"
    assert result.blocked_by_risk is True
    assert "severe_event_risk_override" in result.reasons


def test_map_signal_downgrades_for_mild_risk_event() -> None:
    result = map_signal(
        SignalMappingInput(
            asset_symbol="AMZN",
            score=73.0,
            confidence=0.82,
            technical_score=76.0,
            fundamental_score=70.0,
            sentiment_risk_score=58.0,
            risk_flag=True,
            event_type="litigation",
            unavailable_components=[],
        )
    )

    assert result.signal == "watch"
    assert "downgraded_mild_event_risk" in result.reasons


def test_map_signal_downgrades_strong_buy_on_low_confidence() -> None:
    result = map_signal(
        SignalMappingInput(
            asset_symbol="NFLX",
            score=86.0,
            confidence=0.62,
            technical_score=84.0,
            fundamental_score=79.0,
            sentiment_risk_score=65.0,
            risk_flag=False,
            event_type=None,
            unavailable_components=[],
        )
    )

    assert result.signal == "buy"


def test_map_signal_returns_watch_when_score_missing() -> None:
    result = map_signal(
        SignalMappingInput(
            asset_symbol="META",
            score=None,
            confidence=0.8,
            technical_score=80.0,
            fundamental_score=70.0,
            sentiment_risk_score=60.0,
            risk_flag=False,
            event_type=None,
            unavailable_components=["technical_strength"],
        )
    )

    assert result.signal == "watch"
    assert "missing_composite_score" in result.reasons


def test_map_signal_from_score_explanation_maps_consistently() -> None:
    composite = compute_composite_score(
        CompositeScoreInputs(
            asset_symbol="AAPL",
            as_of_ts=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
            technical_inputs=TechnicalFactorInputs(
                trend_regime="bullish",
                trend_confidence=0.90,
                breakout_signal="upside_breakout",
                breakout_confidence=0.85,
                relative_volume_state="spike",
                relative_volume_ratio=2.0,
            ),
            fundamentals_quality_score=76.0,
            sentiment_risk_inputs=SentimentRiskFactorInputs(
                weighted_sentiment=0.18,
                normalized_sentiment_score=None,
                event_type=None,
                risk_flag=False,
            ),
        )
    )
    payload = build_score_explanation_payload(composite).payload
    result = map_signal_from_score_explanation(payload)

    assert result.signal in {"strong_buy", "buy"}
    assert result.label in {"Strong Buy", "Buy"}
