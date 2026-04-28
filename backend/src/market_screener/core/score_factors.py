"""Score component weights and factor transforms for score model v1."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

SCORE_MODEL_VERSION = "v1.0.1"

SCORE_COMPONENT_WEIGHTS = {
    "technical_strength": 0.45,
    "fundamental_quality": 0.35,
    "sentiment_event_risk": 0.20,
}

TECHNICAL_FACTOR_WEIGHTS = {
    "trend_regime": 0.50,
    "breakout_signal": 0.30,
    "relative_volume": 0.20,
}

_TREND_BASE_SCORES = {
    "bullish": 85.0,
    "accumulation": 70.0,
    "range": 55.0,
    "distribution": 40.0,
    "bearish": 20.0,
    "unknown": 50.0,
}

_BREAKOUT_BASE_SCORES = {
    "upside_breakout": 82.0,
    "none": 52.0,
    "downside_breakout": 20.0,
    "unknown": 50.0,
}

_EVENT_RISK_PENALTIES = {
    "fraud_or_accounting": 28.0,
    "regulatory": 22.0,
    "distress": 24.0,
    "security_incident": 22.0,
    "litigation": 16.0,
    "earnings_warning": 14.0,
    "sentiment_shock": 10.0,
}


@dataclass(frozen=True)
class TransformProfile:
    """Tunable parameters for factor transforms (keep weights unchanged).

    Changing these values should bump SCORE_MODEL_VERSION so results stay auditable.
    """

    confidence_floor: float = 0.40
    confidence_power: float = 1.20
    weighted_sentiment_logistic_k: float = 3.0


DEFAULT_TRANSFORM_PROFILE = TransformProfile()


@dataclass(frozen=True)
class TechnicalFactorInputs:
    """Inputs used to transform technical factors into a 0-100 score."""

    trend_regime: str | None
    trend_confidence: float | None
    breakout_signal: str | None
    breakout_confidence: float | None
    relative_volume_state: str | None
    relative_volume_ratio: float | None


@dataclass(frozen=True)
class TechnicalFactorTransformResult:
    """Transformed technical factor outputs and diagnostics."""

    score: float | None
    factor_scores: dict[str, float | None]
    configured_weights: dict[str, float]
    effective_weights: dict[str, float]
    unavailable_factors: list[str]


@dataclass(frozen=True)
class SentimentRiskFactorInputs:
    """Inputs used to transform sentiment+risk into a 0-100 score."""

    weighted_sentiment: float | None
    normalized_sentiment_score: float | None
    event_type: str | None
    risk_flag: bool | None


@dataclass(frozen=True)
class SentimentRiskTransformResult:
    """Transformed sentiment+risk output and diagnostics."""

    score: float | None
    base_sentiment_score: float | None
    risk_penalty: float
    diagnostics: dict[str, float | str | bool | None]


def normalized_score_component_weights(
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Return normalized score component weights."""

    raw = dict(weights or SCORE_COMPONENT_WEIGHTS)
    if not raw:
        raise ValueError("at least one component weight is required")

    total = 0.0
    for value in raw.values():
        if value < 0:
            raise ValueError("component weights must be non-negative")
        total += value
    if total <= 0:
        raise ValueError("component weight sum must be greater than zero")

    return {name: value / total for name, value in raw.items()}


def transform_technical_strength(
    inputs: TechnicalFactorInputs,
    *,
    profile: TransformProfile = DEFAULT_TRANSFORM_PROFILE,
) -> TechnicalFactorTransformResult:
    """Transform technical factors into a normalized 0-100 technical score."""

    trend_score = _trend_score(inputs.trend_regime, inputs.trend_confidence, profile)
    breakout_score = _breakout_score(inputs.breakout_signal, inputs.breakout_confidence, profile)
    relative_volume_score = _relative_volume_score(
        inputs.relative_volume_state,
        inputs.relative_volume_ratio,
    )

    factor_scores: dict[str, float | None] = {
        "trend_regime": trend_score,
        "breakout_signal": breakout_score,
        "relative_volume": relative_volume_score,
    }
    unavailable = [name for name, value in factor_scores.items() if value is None]

    available_weight_sum = sum(
        TECHNICAL_FACTOR_WEIGHTS[name] for name, value in factor_scores.items() if value is not None
    )
    if available_weight_sum <= 0:
        effective_weights = {name: 0.0 for name in TECHNICAL_FACTOR_WEIGHTS}
        return TechnicalFactorTransformResult(
            score=None,
            factor_scores=factor_scores,
            configured_weights=dict(TECHNICAL_FACTOR_WEIGHTS),
            effective_weights=effective_weights,
            unavailable_factors=unavailable,
        )

    effective_weights = {
        name: (
            0.0
            if factor_scores[name] is None
            else TECHNICAL_FACTOR_WEIGHTS[name] / available_weight_sum
        )
        for name in TECHNICAL_FACTOR_WEIGHTS
    }
    score = sum(
        (factor_scores[name] or 0.0) * effective_weights[name] for name in TECHNICAL_FACTOR_WEIGHTS
    )
    return TechnicalFactorTransformResult(
        score=_clamp(score),
        factor_scores=factor_scores,
        configured_weights=dict(TECHNICAL_FACTOR_WEIGHTS),
        effective_weights=effective_weights,
        unavailable_factors=unavailable,
    )


def transform_fundamental_quality(fundamentals_quality_score: float | None) -> float | None:
    """Clamp fundamentals quality score into 0-100 for model input."""

    if fundamentals_quality_score is None:
        return None
    return _clamp(fundamentals_quality_score)


def transform_sentiment_event_risk(
    inputs: SentimentRiskFactorInputs,
    *,
    profile: TransformProfile = DEFAULT_TRANSFORM_PROFILE,
) -> SentimentRiskTransformResult:
    """Transform sentiment and event-risk inputs into a 0-100 score."""

    base_score = _sentiment_base_score(
        inputs.weighted_sentiment,
        inputs.normalized_sentiment_score,
        profile=profile,
    )

    penalty = 0.0
    normalized_event_type = (inputs.event_type or "").strip().lower() or None
    if inputs.risk_flag:
        penalty = _EVENT_RISK_PENALTIES.get(normalized_event_type or "", 12.0)
        if inputs.weighted_sentiment is not None and inputs.weighted_sentiment <= -0.60:
            penalty += 4.0

    if base_score is None:
        final_score: float | None = None
    else:
        final_score = _clamp(base_score - penalty)

    return SentimentRiskTransformResult(
        score=final_score,
        base_sentiment_score=base_score,
        risk_penalty=penalty,
        diagnostics={
            "weighted_sentiment": inputs.weighted_sentiment,
            "normalized_sentiment_score": inputs.normalized_sentiment_score,
            "event_type": normalized_event_type,
            "risk_flag": bool(inputs.risk_flag),
        },
    )


def _trend_score(
    regime: str | None, confidence: float | None, profile: TransformProfile
) -> float | None:
    if regime is None:
        return None
    key = regime.strip().lower() or "unknown"
    base = _TREND_BASE_SCORES.get(key, _TREND_BASE_SCORES["unknown"])
    return _apply_confidence(base, confidence, profile)


def _breakout_score(
    signal: str | None, confidence: float | None, profile: TransformProfile
) -> float | None:
    if signal is None:
        return None
    key = signal.strip().lower() or "unknown"
    base = _BREAKOUT_BASE_SCORES.get(key, _BREAKOUT_BASE_SCORES["unknown"])
    return _apply_confidence(base, confidence, profile)


def _relative_volume_score(state: str | None, ratio: float | None) -> float | None:
    if state is None and ratio is None:
        return None

    key = (state or "").strip().lower() or "unknown"
    ratio_value = ratio if ratio is None else max(0.0, ratio)

    if key == "spike":
        base = 70.0
        bonus = 0.0 if ratio_value is None else min(20.0, max(0.0, (ratio_value - 1.5) * 20.0))
        return _clamp(base + bonus)
    if key == "dry_up":
        base = 35.0
        penalty = 0.0 if ratio_value is None else min(20.0, max(0.0, (0.7 - ratio_value) * 40.0))
        return _clamp(base - penalty)
    if key == "normal":
        if ratio_value is None:
            return 55.0
        stability_penalty = min(6.0, abs(ratio_value - 1.0) * 10.0)
        return _clamp(56.0 - stability_penalty)
    return 50.0


def _sentiment_base_score(
    weighted_sentiment: float | None,
    normalized_sentiment_score: float | None,
    *,
    profile: TransformProfile,
) -> float | None:
    if normalized_sentiment_score is not None:
        return _clamp(normalized_sentiment_score)
    if weighted_sentiment is None:
        return None

    # Logistic mapping keeps mid-range nuanced while bounding extremes.
    ws = _clamp(weighted_sentiment, -1.0, 1.0)
    k = max(0.1, float(profile.weighted_sentiment_logistic_k))
    score = 100.0 / (1.0 + exp(-k * ws))
    return _clamp(score)


def _apply_confidence(
    base_score: float,
    confidence: float | None,
    profile: TransformProfile,
) -> float:
    raw_confidence = 0.5 if confidence is None else _clamp(confidence, 0.0, 1.0)
    floor = _clamp(profile.confidence_floor, 0.0, 1.0)
    shaped = max(0.0, min(1.0, raw_confidence)) ** max(0.1, float(profile.confidence_power))
    normalized_confidence = floor + (1.0 - floor) * shaped

    adjusted = 50.0 + ((base_score - 50.0) * normalized_confidence)
    return _clamp(adjusted)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def main() -> None:
    """CLI entrypoint for Day 61 score-factor transform smoke check."""

    technical = transform_technical_strength(
        TechnicalFactorInputs(
            trend_regime="bullish",
            trend_confidence=0.90,
            breakout_signal="upside_breakout",
            breakout_confidence=0.85,
            relative_volume_state="spike",
            relative_volume_ratio=2.0,
        )
    )
    sentiment = transform_sentiment_event_risk(
        SentimentRiskFactorInputs(
            weighted_sentiment=0.35,
            normalized_sentiment_score=None,
            event_type=None,
            risk_flag=False,
        )
    )
    print(
        "score_factors:"
        f" model_version={SCORE_MODEL_VERSION}"
        f" technical_score={None if technical.score is None else round(technical.score, 2)}"
        f" sentiment_score={None if sentiment.score is None else round(sentiment.score, 2)}"
    )


if __name__ == "__main__":
    main()
