"""Tests for score weights and factor transforms (Day 61)."""

from __future__ import annotations

from market_screener.core.score_factors import (
    SCORE_COMPONENT_WEIGHTS,
    SCORE_MODEL_VERSION,
    SentimentRiskFactorInputs,
    TechnicalFactorInputs,
    normalized_score_component_weights,
    transform_fundamental_quality,
    transform_sentiment_event_risk,
    transform_technical_strength,
)


def test_score_component_weights_are_normalized() -> None:
    normalized = normalized_score_component_weights()

    assert SCORE_MODEL_VERSION == "v1.0.0"
    assert set(normalized.keys()) == set(SCORE_COMPONENT_WEIGHTS.keys())
    assert round(sum(normalized.values()), 6) == 1.0
    assert round(normalized["technical_strength"], 2) == 0.45
    assert round(normalized["fundamental_quality"], 2) == 0.35
    assert round(normalized["sentiment_event_risk"], 2) == 0.20


def test_score_component_weights_reject_zero_sum() -> None:
    try:
        normalized_score_component_weights({"technical_strength": 0.0})
    except ValueError as exc:
        assert "sum" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError for zero-sum weights")


def test_transform_technical_strength_returns_high_score_for_bullish_stack() -> None:
    result = transform_technical_strength(
        TechnicalFactorInputs(
            trend_regime="bullish",
            trend_confidence=0.90,
            breakout_signal="upside_breakout",
            breakout_confidence=0.85,
            relative_volume_state="spike",
            relative_volume_ratio=2.2,
        )
    )

    assert result.score is not None
    assert result.score >= 75.0
    assert result.unavailable_factors == []
    assert round(sum(result.effective_weights.values()), 6) == 1.0


def test_transform_technical_strength_returns_low_score_for_bearish_stack() -> None:
    result = transform_technical_strength(
        TechnicalFactorInputs(
            trend_regime="bearish",
            trend_confidence=0.95,
            breakout_signal="downside_breakout",
            breakout_confidence=0.90,
            relative_volume_state="dry_up",
            relative_volume_ratio=0.35,
        )
    )

    assert result.score is not None
    assert result.score <= 30.0


def test_transform_technical_strength_reweights_missing_factors() -> None:
    result = transform_technical_strength(
        TechnicalFactorInputs(
            trend_regime="range",
            trend_confidence=0.60,
            breakout_signal=None,
            breakout_confidence=None,
            relative_volume_state=None,
            relative_volume_ratio=None,
        )
    )

    assert result.score is not None
    assert set(result.unavailable_factors) == {"breakout_signal", "relative_volume"}
    assert result.effective_weights["trend_regime"] == 1.0


def test_transform_fundamental_quality_clamps_out_of_bounds() -> None:
    assert transform_fundamental_quality(-8.0) == 0.0
    assert transform_fundamental_quality(140.0) == 100.0
    assert transform_fundamental_quality(None) is None


def test_transform_sentiment_event_risk_penalizes_high_risk_event() -> None:
    result = transform_sentiment_event_risk(
        SentimentRiskFactorInputs(
            weighted_sentiment=0.30,
            normalized_sentiment_score=72.0,
            event_type="fraud_or_accounting",
            risk_flag=True,
        )
    )

    assert result.base_sentiment_score == 72.0
    assert result.risk_penalty >= 28.0
    assert result.score is not None
    assert result.score <= 44.0


def test_transform_sentiment_event_risk_uses_weighted_fallback_when_normalized_missing() -> None:
    result = transform_sentiment_event_risk(
        SentimentRiskFactorInputs(
            weighted_sentiment=0.20,
            normalized_sentiment_score=None,
            event_type=None,
            risk_flag=False,
        )
    )

    assert result.base_sentiment_score is not None
    assert result.score is not None
    assert round(result.score, 2) == 60.0


def test_transform_sentiment_event_risk_returns_none_when_no_sentiment_inputs() -> None:
    result = transform_sentiment_event_risk(
        SentimentRiskFactorInputs(
            weighted_sentiment=None,
            normalized_sentiment_score=None,
            event_type="regulatory",
            risk_flag=True,
        )
    )

    assert result.base_sentiment_score is None
    assert result.score is None
