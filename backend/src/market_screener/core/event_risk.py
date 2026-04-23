"""Event-risk tagging helpers for news articles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventRiskInput:
    """Inputs used to classify event risk from article content."""

    title: str | None
    description: str | None
    sentiment_score: float | None


@dataclass(frozen=True)
class EventRiskTagResult:
    """Tagged event-risk output for one article."""

    event_type: str | None
    risk_flag: bool
    rule_hits: list[str]
    matched_keywords: list[str]
    sentiment_risk: bool


_EVENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "fraud_or_accounting",
        (
            "fraud",
            "accounting fraud",
            "accounting irregularities",
            "misstatement",
            "restatement",
            "embezzlement",
        ),
    ),
    (
        "regulatory",
        (
            "regulator",
            "regulatory probe",
            "sec probe",
            "investigation",
            "ban",
            "sanction",
            "compliance breach",
        ),
    ),
    (
        "litigation",
        (
            "lawsuit",
            "class action",
            "litigation",
            "legal dispute",
            "court filing",
            "settlement",
        ),
    ),
    (
        "distress",
        (
            "bankruptcy",
            "insolvency",
            "default",
            "chapter 11",
            "restructuring",
            "debt crisis",
        ),
    ),
    (
        "security_incident",
        (
            "breach",
            "hack",
            "cyberattack",
            "exploit",
            "data leak",
            "ransomware",
        ),
    ),
    (
        "earnings_warning",
        (
            "profit warning",
            "guidance cut",
            "cuts outlook",
            "misses estimates",
            "earnings miss",
            "downgrade",
        ),
    ),
)


def tag_event_risk(
    input_item: EventRiskInput,
    *,
    negative_sentiment_threshold: float = -0.35,
) -> EventRiskTagResult:
    """Tag article event risk from rule-based keyword and sentiment checks."""

    text = " ".join(
        part.strip().lower()
        for part in (input_item.title or "", input_item.description or "")
        if part and part.strip()
    )

    selected_event_type: str | None = None
    matched_keywords: list[str] = []
    rule_hits: list[str] = []

    if text:
        for event_type, keywords in _EVENT_RULES:
            matched = [keyword for keyword in keywords if keyword in text]
            if matched:
                selected_event_type = event_type
                matched_keywords = matched
                rule_hits.append(f"keyword:{event_type}")
                break

    sentiment_value = _to_float(input_item.sentiment_score)
    sentiment_risk = sentiment_value is not None and sentiment_value <= negative_sentiment_threshold
    if sentiment_risk:
        rule_hits.append("sentiment:negative_shock")

    risk_flag = bool(selected_event_type is not None or sentiment_risk)
    if selected_event_type is None and sentiment_risk:
        selected_event_type = "sentiment_shock"

    return EventRiskTagResult(
        event_type=selected_event_type,
        risk_flag=risk_flag,
        rule_hits=rule_hits,
        matched_keywords=matched_keywords,
        sentiment_risk=sentiment_risk,
    )


def _to_float(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def main() -> None:
    """CLI entrypoint for event-risk tagging smoke check."""

    result = tag_event_risk(
        EventRiskInput(
            title="Company faces SEC probe after accounting fraud allegations",
            description="Shares fall after investigation report.",
            sentiment_score=-0.2,
        )
    )
    print(
        "event_risk_tagging:"
        f" event_type={result.event_type}"
        f" risk_flag={result.risk_flag}"
        f" rule_hits={len(result.rule_hits)}"
        f" matched_keywords={len(result.matched_keywords)}"
    )


if __name__ == "__main__":
    main()
