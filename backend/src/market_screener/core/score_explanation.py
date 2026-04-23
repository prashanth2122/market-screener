"""Score explanation payload builder per asset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from market_screener.core.composite_score import (
    COMPONENT_ORDER,
    CompositeScoreInputs,
    CompositeScoreResult,
    compute_composite_score,
)
from market_screener.core.score_factors import (
    SentimentRiskFactorInputs,
    TechnicalFactorInputs,
)

_COMPONENT_LABELS = {
    "technical_strength": "technical",
    "fundamental_quality": "fundamental",
    "sentiment_event_risk": "sentiment_risk",
}


@dataclass(frozen=True)
class ScoreExplanationPayload:
    """JSON-ready score explanation payload for a single asset."""

    payload: dict[str, Any]


def build_score_explanation_payload(
    result: CompositeScoreResult,
    *,
    top_driver_count: int = 2,
) -> ScoreExplanationPayload:
    """Build score explanation payload from composite score output."""

    normalized_top_count = max(1, top_driver_count)
    component_breakdown: list[dict[str, Any]] = []
    driver_edges: list[dict[str, Any]] = []

    gaps: list[str] = [f"component:{name}" for name in result.unavailable_components]
    if result.technical_details is not None:
        for factor in result.technical_details.unavailable_factors:
            gaps.append(f"technical_factor:{factor}")

    for component in COMPONENT_ORDER:
        component_score = result.component_scores.get(component)
        effective_weight = float(result.effective_weights.get(component, 0.0))
        contribution = float(result.component_contributions.get(component, 0.0))
        neutral_contribution = effective_weight * 50.0
        edge_points = contribution - neutral_contribution

        impact = "neutral"
        if edge_points > 0.5:
            impact = "positive"
        elif edge_points < -0.5:
            impact = "negative"

        breakdown_item = {
            "component": _COMPONENT_LABELS.get(component, component),
            "score": component_score,
            "effective_weight": effective_weight,
            "contribution_points": contribution,
            "edge_vs_neutral_points": edge_points,
            "impact": impact,
            "rationale": _component_rationale(component, result),
        }
        component_breakdown.append(breakdown_item)

        if component_score is None:
            continue
        driver_edges.append(
            {
                "component": _COMPONENT_LABELS.get(component, component),
                "score": component_score,
                "edge_vs_neutral_points": edge_points,
                "rationale": breakdown_item["rationale"],
            }
        )

    positive = [
        item
        for item in sorted(
            driver_edges, key=lambda row: row["edge_vs_neutral_points"], reverse=True
        )
        if item["edge_vs_neutral_points"] > 0
    ][:normalized_top_count]
    negative = [
        item
        for item in sorted(driver_edges, key=lambda row: row["edge_vs_neutral_points"])
        if item["edge_vs_neutral_points"] < 0
    ][:normalized_top_count]

    payload = {
        "asset_symbol": result.asset_symbol,
        "as_of_ts": None if result.as_of_ts is None else result.as_of_ts.isoformat(),
        "model_version": result.model_version,
        "score": result.score,
        "score_band": _score_band(result.score),
        "confidence": _confidence_score(result),
        "summary": _summary_line(result, positive, negative),
        "component_breakdown": component_breakdown,
        "top_positive_drivers": positive,
        "top_negative_drivers": negative,
        "risk_context": _risk_context(result),
        "gaps": gaps,
    }
    return ScoreExplanationPayload(payload=payload)


def _component_rationale(component: str, result: CompositeScoreResult) -> str:
    if component == "technical_strength":
        if result.technical_details is None:
            return "technical transform unavailable"
        factor_scores = result.technical_details.factor_scores
        available = {name: value for name, value in factor_scores.items() if value is not None}
        if not available:
            return "no technical factors available"
        dominant = max(available.items(), key=lambda item: item[1])[0]
        return f"dominant factor={dominant}"

    if component == "fundamental_quality":
        score = result.component_scores.get(component)
        if score is None:
            return "fundamentals score unavailable"
        if score >= 70:
            return "fundamentals quality supports score"
        if score >= 50:
            return "fundamentals quality mixed"
        return "fundamentals quality drags score"

    if component == "sentiment_event_risk":
        if result.sentiment_risk_details is None:
            return "sentiment/risk transform unavailable"
        penalty = result.sentiment_risk_details.risk_penalty
        if penalty > 0:
            return f"event-risk penalty applied={round(penalty, 2)}"
        return "sentiment context without event-risk penalty"

    return "n/a"


def _score_band(score: float | None) -> str:
    if score is None:
        return "unavailable"
    if score >= 80:
        return "high"
    if score >= 65:
        return "constructive"
    if score >= 50:
        return "mixed"
    return "weak"


def _confidence_score(result: CompositeScoreResult) -> float:
    confidence = 1.0 - (0.22 * len(result.unavailable_components))
    if result.technical_details is not None:
        confidence -= 0.04 * len(result.technical_details.unavailable_factors)
    return _clamp(round(confidence, 2), minimum=0.2, maximum=1.0)


def _summary_line(
    result: CompositeScoreResult,
    positive: list[dict[str, Any]],
    negative: list[dict[str, Any]],
) -> str:
    if result.score is None:
        return "Composite score unavailable due to missing component coverage."

    band = _score_band(result.score)
    lead_positive = positive[0]["component"] if positive else "none"
    lead_negative = negative[0]["component"] if negative else "none"
    return (
        f"Composite score {round(result.score, 2)} ({band}); "
        f"primary support={lead_positive}, primary drag={lead_negative}."
    )


def _risk_context(result: CompositeScoreResult) -> dict[str, Any]:
    details = result.sentiment_risk_details
    if details is None:
        return {
            "sentiment_score": None,
            "risk_penalty": 0.0,
            "risk_flag": None,
            "event_type": None,
        }
    diagnostics = details.diagnostics
    return {
        "sentiment_score": details.base_sentiment_score,
        "risk_penalty": details.risk_penalty,
        "risk_flag": diagnostics.get("risk_flag"),
        "event_type": diagnostics.get("event_type"),
    }


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def main() -> None:
    """CLI entrypoint for score explanation payload smoke check."""

    now = datetime.now(UTC)
    composite = compute_composite_score(
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
    explanation = build_score_explanation_payload(composite)
    print(
        "score_explanation:"
        f" symbol={explanation.payload.get('asset_symbol')}"
        f" score={explanation.payload.get('score')}"
        f" band={explanation.payload.get('score_band')}"
        f" confidence={explanation.payload.get('confidence')}"
        f" gaps={len(explanation.payload.get('gaps') or [])}"
    )


if __name__ == "__main__":
    main()
