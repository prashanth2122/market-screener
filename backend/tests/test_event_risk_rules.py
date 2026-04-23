"""Tests for event-risk tagging helper rules."""

from __future__ import annotations

from market_screener.core.event_risk import EventRiskInput, tag_event_risk


def test_tag_event_risk_detects_fraud_keywords() -> None:
    result = tag_event_risk(
        EventRiskInput(
            title="Company faces accounting fraud probe",
            description=None,
            sentiment_score=-0.1,
        )
    )

    assert result.event_type == "fraud_or_accounting"
    assert result.risk_flag is True
    assert "keyword:fraud_or_accounting" in result.rule_hits
    assert "fraud" in result.matched_keywords


def test_tag_event_risk_detects_regulatory_keywords() -> None:
    result = tag_event_risk(
        EventRiskInput(
            title="Regulatory probe starts after compliance breach report",
            description=None,
            sentiment_score=0.0,
        )
    )

    assert result.event_type == "regulatory"
    assert result.risk_flag is True
    assert any("keyword:" in hit for hit in result.rule_hits)


def test_tag_event_risk_triggers_sentiment_shock_without_keyword() -> None:
    result = tag_event_risk(
        EventRiskInput(
            title="Analyst update",
            description="Market sentiment turns sharply lower.",
            sentiment_score=-0.65,
        ),
        negative_sentiment_threshold=-0.35,
    )

    assert result.event_type == "sentiment_shock"
    assert result.risk_flag is True
    assert result.sentiment_risk is True
    assert result.matched_keywords == []


def test_tag_event_risk_returns_non_risk_for_benign_news() -> None:
    result = tag_event_risk(
        EventRiskInput(
            title="Company launches new product line",
            description="Expansion plan remains on track.",
            sentiment_score=0.2,
        )
    )

    assert result.event_type is None
    assert result.risk_flag is False
    assert result.rule_hits == []
    assert result.matched_keywords == []


def test_tag_event_risk_uses_rule_precedence_when_multiple_keywords_match() -> None:
    result = tag_event_risk(
        EventRiskInput(
            title="Fraud lawsuit emerges after probe",
            description=None,
            sentiment_score=-0.4,
        )
    )

    assert result.event_type == "fraud_or_accounting"
    assert result.risk_flag is True
