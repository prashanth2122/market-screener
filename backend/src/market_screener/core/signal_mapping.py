"""Signal mapping rules from composite score outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from market_screener.core.composite_score import CompositeScoreInputs, compute_composite_score
from market_screener.core.score_explanation import build_score_explanation_payload
from market_screener.core.score_factors import SentimentRiskFactorInputs, TechnicalFactorInputs

VALID_SIGNALS = {
    "strong_buy",
    "buy",
    "watch",
    "avoid",
}

SEVERE_RISK_EVENT_TYPES = {
    "fraud_or_accounting",
    "regulatory",
    "distress",
    "security_incident",
}

MILD_RISK_EVENT_TYPES = {
    "litigation",
    "earnings_warning",
    "sentiment_shock",
}

SIGNAL_LABELS = {
    "strong_buy": "Strong Buy",
    "buy": "Buy",
    "watch": "Watch",
    "avoid": "Avoid",
}


@dataclass(frozen=True)
class SignalMappingInput:
    """Inputs used to map one asset into a signal bucket."""

    asset_symbol: str | None
    score: float | None
    confidence: float | None
    technical_score: float | None
    fundamental_score: float | None
    sentiment_risk_score: float | None
    risk_flag: bool | None
    event_type: str | None
    unavailable_components: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SignalMappingResult:
    """Signal mapping result with traceable rationale."""

    asset_symbol: str | None
    signal: str
    label: str
    score: float | None
    confidence: float | None
    blocked_by_risk: bool
    reasons: list[str]


def map_signal(input_item: SignalMappingInput) -> SignalMappingResult:
    """Map score + risk context into Strong Buy / Buy / Watch / Avoid."""

    reasons: list[str] = []
    normalized_event_type = (input_item.event_type or "").strip().lower() or None
    has_risk_flag = bool(input_item.risk_flag)

    if has_risk_flag and normalized_event_type in SEVERE_RISK_EVENT_TYPES:
        reasons.append("severe_event_risk_override")
        return _result(
            asset_symbol=input_item.asset_symbol,
            signal="avoid",
            score=input_item.score,
            confidence=input_item.confidence,
            blocked_by_risk=True,
            reasons=reasons,
        )

    if input_item.score is None:
        reasons.append("missing_composite_score")
        return _result(
            asset_symbol=input_item.asset_symbol,
            signal="watch",
            score=None,
            confidence=input_item.confidence,
            blocked_by_risk=False,
            reasons=reasons,
        )

    signal = _score_to_signal(input_item.score)
    reasons.append(f"score_bucket={signal}")

    if signal == "strong_buy":
        if input_item.confidence is not None and input_item.confidence < 0.75:
            signal = _downgrade(signal)
            reasons.append("downgraded_low_confidence_for_strong_buy")
        if input_item.technical_score is not None and input_item.technical_score < 70.0:
            signal = _downgrade(signal)
            reasons.append("downgraded_technical_floor")
        if input_item.fundamental_score is not None and input_item.fundamental_score < 65.0:
            signal = _downgrade(signal)
            reasons.append("downgraded_fundamental_floor")
        if input_item.sentiment_risk_score is not None and input_item.sentiment_risk_score < 55.0:
            signal = _downgrade(signal)
            reasons.append("downgraded_sentiment_floor")

    if has_risk_flag:
        if normalized_event_type in MILD_RISK_EVENT_TYPES:
            signal = _downgrade(signal)
            reasons.append("downgraded_mild_event_risk")
        elif normalized_event_type is None and signal in {"strong_buy", "buy"}:
            signal = _downgrade(signal)
            reasons.append("downgraded_untyped_risk_flag")

    if input_item.confidence is not None and input_item.confidence < 0.55:
        signal = _downgrade(signal)
        reasons.append("downgraded_low_confidence")

    if len(input_item.unavailable_components) >= 2 and signal in {"strong_buy", "buy"}:
        signal = _downgrade(signal)
        reasons.append("downgraded_component_coverage_gap")

    if input_item.sentiment_risk_score is not None and input_item.sentiment_risk_score < 35.0:
        signal = "avoid"
        reasons.append("sentiment_risk_floor_avoid")

    blocked_by_risk = signal == "avoid" and has_risk_flag
    return _result(
        asset_symbol=input_item.asset_symbol,
        signal=signal,
        score=input_item.score,
        confidence=input_item.confidence,
        blocked_by_risk=blocked_by_risk,
        reasons=reasons,
    )


def map_signal_from_score_explanation(payload: dict[str, Any]) -> SignalMappingResult:
    """Map signal from score explanation payload."""

    breakdown = payload.get("component_breakdown") or []
    component_scores = {
        str(item.get("component")): item.get("score")
        for item in breakdown
        if isinstance(item, dict)
    }
    risk_context = payload.get("risk_context") or {}
    gaps = payload.get("gaps") or []
    unavailable_components: list[str] = []
    for entry in gaps:
        if not isinstance(entry, str):
            continue
        if entry.startswith("component:"):
            unavailable_components.append(entry.removeprefix("component:"))

    input_item = SignalMappingInput(
        asset_symbol=payload.get("asset_symbol"),
        score=_to_float(payload.get("score")),
        confidence=_to_float(payload.get("confidence")),
        technical_score=_to_float(component_scores.get("technical")),
        fundamental_score=_to_float(component_scores.get("fundamental")),
        sentiment_risk_score=_to_float(component_scores.get("sentiment_risk")),
        risk_flag=_to_bool_or_none(risk_context.get("risk_flag")),
        event_type=_to_str_or_none(risk_context.get("event_type")),
        unavailable_components=unavailable_components,
    )
    return map_signal(input_item)


def _score_to_signal(score: float) -> str:
    if score >= 80.0:
        return "strong_buy"
    if score >= 65.0:
        return "buy"
    if score >= 50.0:
        return "watch"
    return "avoid"


def _downgrade(signal: str) -> str:
    if signal == "strong_buy":
        return "buy"
    if signal == "buy":
        return "watch"
    if signal == "watch":
        return "avoid"
    return "avoid"


def _result(
    *,
    asset_symbol: str | None,
    signal: str,
    score: float | None,
    confidence: float | None,
    blocked_by_risk: bool,
    reasons: list[str],
) -> SignalMappingResult:
    if signal not in VALID_SIGNALS:
        raise ValueError(f"unsupported signal: {signal}")
    return SignalMappingResult(
        asset_symbol=asset_symbol,
        signal=signal,
        label=SIGNAL_LABELS[signal],
        score=score,
        confidence=confidence,
        blocked_by_risk=blocked_by_risk,
        reasons=reasons,
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return bool(value)


def _to_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def main() -> None:
    """CLI entrypoint for signal mapping smoke check."""

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
    explanation = build_score_explanation_payload(composite).payload
    signal = map_signal_from_score_explanation(explanation)
    print(
        "signal_mapping:"
        f" symbol={signal.asset_symbol}"
        f" signal={signal.signal}"
        f" label={signal.label}"
        f" blocked_by_risk={signal.blocked_by_risk}"
    )


if __name__ == "__main__":
    main()
