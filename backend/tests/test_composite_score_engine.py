"""Tests for composite score engine v1."""

from __future__ import annotations

from datetime import UTC, datetime

from market_screener.core.composite_score import CompositeScoreInputs, compute_composite_score
from market_screener.core.score_factors import SentimentRiskFactorInputs, TechnicalFactorInputs


def _base_inputs() -> CompositeScoreInputs:
    return CompositeScoreInputs(
        asset_symbol="AAPL",
        as_of_ts=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
        technical_inputs=TechnicalFactorInputs(
            trend_regime="bullish",
            trend_confidence=0.90,
            breakout_signal="upside_breakout",
            breakout_confidence=0.85,
            relative_volume_state="spike",
            relative_volume_ratio=2.1,
        ),
        fundamentals_quality_score=78.0,
        sentiment_risk_inputs=SentimentRiskFactorInputs(
            weighted_sentiment=0.30,
            normalized_sentiment_score=None,
            event_type=None,
            risk_flag=False,
        ),
    )


def test_compute_composite_score_returns_weighted_output_with_all_components() -> None:
    result = compute_composite_score(_base_inputs())

    assert result.model_version == "v1.0.1"
    assert result.score is not None
    assert 70.0 <= result.score <= 95.0
    assert result.unavailable_components == []
    assert round(sum(result.effective_weights.values()), 6) == 1.0
    assert round(result.effective_weights["technical_strength"], 2) == 0.45
    assert round(result.effective_weights["fundamental_quality"], 2) == 0.35
    assert round(result.effective_weights["sentiment_event_risk"], 2) == 0.20


def test_compute_composite_score_reweights_when_sentiment_component_missing() -> None:
    inputs = _base_inputs()
    missing_sentiment = CompositeScoreInputs(
        asset_symbol=inputs.asset_symbol,
        as_of_ts=inputs.as_of_ts,
        technical_inputs=inputs.technical_inputs,
        fundamentals_quality_score=inputs.fundamentals_quality_score,
        sentiment_risk_inputs=None,
    )

    result = compute_composite_score(missing_sentiment)

    assert result.score is not None
    assert result.component_scores["sentiment_event_risk"] is None
    assert "sentiment_event_risk" in result.unavailable_components
    assert round(result.effective_weights["technical_strength"], 6) == round(0.45 / 0.80, 6)
    assert round(result.effective_weights["fundamental_quality"], 6) == round(0.35 / 0.80, 6)
    assert result.effective_weights["sentiment_event_risk"] == 0.0


def test_compute_composite_score_returns_none_when_every_component_missing() -> None:
    result = compute_composite_score(
        CompositeScoreInputs(
            asset_symbol="AAPL",
            as_of_ts=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
            technical_inputs=None,
            fundamentals_quality_score=None,
            sentiment_risk_inputs=None,
        )
    )

    assert result.score is None
    assert len(result.unavailable_components) == 3
    assert all(weight == 0.0 for weight in result.effective_weights.values())
    assert all(value == 0.0 for value in result.component_contributions.values())


def test_compute_composite_score_uses_custom_component_weights() -> None:
    weights = {
        "technical_strength": 0.60,
        "fundamental_quality": 0.20,
        "sentiment_event_risk": 0.20,
    }
    result = compute_composite_score(_base_inputs(), component_weights=weights)

    assert result.score is not None
    assert round(result.configured_weights["technical_strength"], 2) == 0.60
    assert round(result.configured_weights["fundamental_quality"], 2) == 0.20
    assert round(result.configured_weights["sentiment_event_risk"], 2) == 0.20


def test_compute_composite_score_decreases_with_high_risk_penalty() -> None:
    base = _base_inputs()
    no_risk = compute_composite_score(base)
    high_risk = compute_composite_score(
        CompositeScoreInputs(
            asset_symbol=base.asset_symbol,
            as_of_ts=base.as_of_ts,
            technical_inputs=base.technical_inputs,
            fundamentals_quality_score=base.fundamentals_quality_score,
            sentiment_risk_inputs=SentimentRiskFactorInputs(
                weighted_sentiment=-0.65,
                normalized_sentiment_score=55.0,
                event_type="fraud_or_accounting",
                risk_flag=True,
            ),
        )
    )

    assert no_risk.score is not None
    assert high_risk.score is not None
    assert high_risk.score < no_risk.score


def test_compute_composite_score_raises_on_invalid_component_weights() -> None:
    try:
        compute_composite_score(
            _base_inputs(),
            component_weights={
                "technical_strength": 0.45,
                "fundamental_quality": -0.1,
                "sentiment_event_risk": 0.2,
            },
        )
    except ValueError as exc:
        assert "non-negative" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError for negative weight input")


def test_compute_composite_score_includes_component_contributions() -> None:
    result = compute_composite_score(_base_inputs())

    assert result.score is not None
    assert round(sum(result.component_contributions.values()), 6) == round(result.score, 6)
    assert set(result.component_contributions.keys()) == {
        "technical_strength",
        "fundamental_quality",
        "sentiment_event_risk",
    }
