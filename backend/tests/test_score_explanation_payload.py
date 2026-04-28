"""Tests for score explanation payload generation."""

from __future__ import annotations

from datetime import UTC, datetime

from market_screener.core.composite_score import CompositeScoreInputs, compute_composite_score
from market_screener.core.score_explanation import build_score_explanation_payload
from market_screener.core.score_factors import SentimentRiskFactorInputs, TechnicalFactorInputs


def _composite_result_with_full_inputs():
    return compute_composite_score(
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


def test_build_score_explanation_payload_contains_expected_sections() -> None:
    result = _composite_result_with_full_inputs()
    payload = build_score_explanation_payload(result).payload

    assert payload["asset_symbol"] == "AAPL"
    assert payload["model_version"] == "v1.0.1"
    assert isinstance(payload["score"], float)
    assert payload["score_band"] in {"high", "constructive", "mixed", "weak", "unavailable"}
    assert 0.2 <= payload["confidence"] <= 1.0
    assert isinstance(payload["summary"], str)
    assert isinstance(payload["component_breakdown"], list)
    assert len(payload["component_breakdown"]) == 3
    assert isinstance(payload["top_positive_drivers"], list)
    assert isinstance(payload["top_negative_drivers"], list)
    assert isinstance(payload["risk_context"], dict)
    assert isinstance(payload["gaps"], list)


def test_build_score_explanation_payload_includes_component_rationales() -> None:
    payload = build_score_explanation_payload(_composite_result_with_full_inputs()).payload
    breakdown = payload["component_breakdown"]
    rationales = {item["component"]: item["rationale"] for item in breakdown}

    assert "technical" in rationales
    assert "fundamental" in rationales
    assert "sentiment_risk" in rationales
    assert "dominant factor=" in rationales["technical"]


def test_build_score_explanation_payload_reports_missing_components_as_gaps() -> None:
    result = compute_composite_score(
        CompositeScoreInputs(
            asset_symbol="AAPL",
            as_of_ts=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
            technical_inputs=None,
            fundamentals_quality_score=60.0,
            sentiment_risk_inputs=None,
        )
    )
    payload = build_score_explanation_payload(result).payload

    assert "component:technical_strength" in payload["gaps"]
    assert "component:sentiment_event_risk" in payload["gaps"]
    assert payload["confidence"] < 1.0


def test_build_score_explanation_payload_handles_unavailable_score() -> None:
    result = compute_composite_score(
        CompositeScoreInputs(
            asset_symbol="AAPL",
            as_of_ts=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
            technical_inputs=None,
            fundamentals_quality_score=None,
            sentiment_risk_inputs=None,
        )
    )
    payload = build_score_explanation_payload(result).payload

    assert payload["score"] is None
    assert payload["score_band"] == "unavailable"
    assert payload["summary"].startswith("Composite score unavailable")


def test_build_score_explanation_payload_includes_risk_context_penalty() -> None:
    result = compute_composite_score(
        CompositeScoreInputs(
            asset_symbol="AAPL",
            as_of_ts=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
            technical_inputs=TechnicalFactorInputs(
                trend_regime="bullish",
                trend_confidence=0.9,
                breakout_signal="upside_breakout",
                breakout_confidence=0.9,
                relative_volume_state="spike",
                relative_volume_ratio=2.1,
            ),
            fundamentals_quality_score=78.0,
            sentiment_risk_inputs=SentimentRiskFactorInputs(
                weighted_sentiment=-0.62,
                normalized_sentiment_score=55.0,
                event_type="fraud_or_accounting",
                risk_flag=True,
            ),
        )
    )
    payload = build_score_explanation_payload(result).payload
    risk_context = payload["risk_context"]

    assert risk_context["risk_flag"] is True
    assert risk_context["event_type"] == "fraud_or_accounting"
    assert float(risk_context["risk_penalty"]) >= 28.0
    assert any(
        "event-risk penalty applied" in item["rationale"]
        for item in payload["component_breakdown"]
        if item["component"] == "sentiment_risk"
    )


def test_build_score_explanation_payload_limits_driver_lists() -> None:
    payload = build_score_explanation_payload(
        _composite_result_with_full_inputs(),
        top_driver_count=1,
    ).payload

    assert len(payload["top_positive_drivers"]) <= 1
    assert len(payload["top_negative_drivers"]) <= 1
