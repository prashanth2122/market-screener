"""Composite score engine v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from market_screener.core.score_factors import (
    SCORE_COMPONENT_WEIGHTS,
    SCORE_MODEL_VERSION,
    SentimentRiskFactorInputs,
    SentimentRiskTransformResult,
    TechnicalFactorInputs,
    TechnicalFactorTransformResult,
    normalized_score_component_weights,
    transform_fundamental_quality,
    transform_sentiment_event_risk,
    transform_technical_strength,
)

COMPONENT_ORDER = (
    "technical_strength",
    "fundamental_quality",
    "sentiment_event_risk",
)


@dataclass(frozen=True)
class CompositeScoreInputs:
    """Inputs for the v1 composite score engine."""

    asset_symbol: str | None
    as_of_ts: datetime | None
    technical_inputs: TechnicalFactorInputs | None
    fundamentals_quality_score: float | None
    sentiment_risk_inputs: SentimentRiskFactorInputs | None


@dataclass(frozen=True)
class CompositeScoreResult:
    """Composite score output with component diagnostics."""

    model_version: str
    asset_symbol: str | None
    as_of_ts: datetime | None
    score: float | None
    component_scores: dict[str, float | None]
    component_contributions: dict[str, float]
    configured_weights: dict[str, float]
    effective_weights: dict[str, float]
    unavailable_components: list[str]
    technical_details: TechnicalFactorTransformResult | None
    sentiment_risk_details: SentimentRiskTransformResult | None


def compute_composite_score(
    inputs: CompositeScoreInputs,
    *,
    component_weights: dict[str, float] | None = None,
) -> CompositeScoreResult:
    """Compute composite score v1 from transformed components."""

    weights = normalized_score_component_weights(component_weights or SCORE_COMPONENT_WEIGHTS)

    technical_details: TechnicalFactorTransformResult | None = None
    if inputs.technical_inputs is not None:
        technical_details = transform_technical_strength(inputs.technical_inputs)
    technical_score = None if technical_details is None else technical_details.score

    fundamentals_score = transform_fundamental_quality(inputs.fundamentals_quality_score)

    sentiment_risk_details: SentimentRiskTransformResult | None = None
    if inputs.sentiment_risk_inputs is not None:
        sentiment_risk_details = transform_sentiment_event_risk(inputs.sentiment_risk_inputs)
    sentiment_risk_score = None if sentiment_risk_details is None else sentiment_risk_details.score

    component_scores: dict[str, float | None] = {
        "technical_strength": technical_score,
        "fundamental_quality": fundamentals_score,
        "sentiment_event_risk": sentiment_risk_score,
    }
    unavailable_components = [name for name in COMPONENT_ORDER if component_scores[name] is None]

    available_weight_sum = sum(
        weights[name] for name in COMPONENT_ORDER if component_scores[name] is not None
    )

    if available_weight_sum <= 0:
        effective_weights = {name: 0.0 for name in COMPONENT_ORDER}
        contributions = {name: 0.0 for name in COMPONENT_ORDER}
        final_score: float | None = None
    else:
        effective_weights = {
            name: (0.0 if component_scores[name] is None else weights[name] / available_weight_sum)
            for name in COMPONENT_ORDER
        }
        contributions = {
            name: (component_scores[name] or 0.0) * effective_weights[name]
            for name in COMPONENT_ORDER
        }
        final_score = _clamp(sum(contributions.values()))

    return CompositeScoreResult(
        model_version=SCORE_MODEL_VERSION,
        asset_symbol=inputs.asset_symbol,
        as_of_ts=inputs.as_of_ts,
        score=final_score,
        component_scores=component_scores,
        component_contributions=contributions,
        configured_weights=weights,
        effective_weights=effective_weights,
        unavailable_components=unavailable_components,
        technical_details=technical_details,
        sentiment_risk_details=sentiment_risk_details,
    )


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def main() -> None:
    """CLI entrypoint for composite score engine smoke check."""

    now = datetime.now(UTC)
    result = compute_composite_score(
        CompositeScoreInputs(
            asset_symbol="AAPL",
            as_of_ts=now,
            technical_inputs=TechnicalFactorInputs(
                trend_regime="bullish",
                trend_confidence=0.88,
                breakout_signal="upside_breakout",
                breakout_confidence=0.81,
                relative_volume_state="spike",
                relative_volume_ratio=1.9,
            ),
            fundamentals_quality_score=77.5,
            sentiment_risk_inputs=SentimentRiskFactorInputs(
                weighted_sentiment=0.24,
                normalized_sentiment_score=None,
                event_type=None,
                risk_flag=False,
            ),
        )
    )
    print(
        "composite_score:"
        f" model_version={result.model_version}"
        f" symbol={result.asset_symbol}"
        f" score={None if result.score is None else round(result.score, 2)}"
        f" unavailable={len(result.unavailable_components)}"
    )


if __name__ == "__main__":
    main()
