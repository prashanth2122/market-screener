"""Tests for sentiment scoring core helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from market_screener.core.sentiment import (
    ArticleSentimentInput,
    WeightedSentimentArticle,
    compute_lexicon_sentiment,
    compute_time_decay_weight,
    compute_weighted_sentiment,
    derive_article_sentiment,
)


def test_compute_lexicon_sentiment_returns_positive_for_positive_keywords() -> None:
    score = compute_lexicon_sentiment("Company beats estimates and reports strong growth gains")

    assert score is not None
    assert score > 0.0


def test_compute_lexicon_sentiment_returns_negative_for_negative_keywords() -> None:
    score = compute_lexicon_sentiment("Shares fall after weak results and fraud probe warning")

    assert score is not None
    assert score < 0.0


def test_derive_article_sentiment_prefers_blended_when_both_sources_available() -> None:
    derived = derive_article_sentiment(
        ArticleSentimentInput(
            published_at=datetime.now(UTC),
            provider_sentiment=0.2,
            title="Company beats estimates with strong profit growth",
            description=None,
        )
    )

    assert derived.method == "blended"
    assert derived.score is not None


def test_derive_article_sentiment_uses_lexicon_when_provider_missing() -> None:
    derived = derive_article_sentiment(
        ArticleSentimentInput(
            published_at=datetime.now(UTC),
            provider_sentiment=None,
            title="Company downgrades outlook after losses",
            description=None,
        )
    )

    assert derived.method == "lexicon"
    assert derived.score is not None
    assert derived.score < 0.0


def test_compute_time_decay_weight_half_life_behavior() -> None:
    assert compute_time_decay_weight(age_hours=0.0, half_life_hours=24) == 1.0
    assert round(compute_time_decay_weight(age_hours=24.0, half_life_hours=24), 4) == 0.5


def test_compute_weighted_sentiment_applies_lookback_and_decay() -> None:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    result = compute_weighted_sentiment(
        [
            WeightedSentimentArticle(published_at=now - timedelta(hours=2), score=0.8),
            WeightedSentimentArticle(published_at=now - timedelta(hours=20), score=-0.2),
            WeightedSentimentArticle(published_at=now - timedelta(hours=90), score=0.9),
            WeightedSentimentArticle(published_at=now - timedelta(hours=1), score=None),
        ],
        now_utc=now,
        lookback_hours=72,
        half_life_hours=24,
    )

    assert result.article_count == 3
    assert result.scored_article_count == 2
    assert result.unavailable_articles == 1
    assert result.weighted_sentiment is not None
    assert result.normalized_score is not None
    assert result.weighted_sentiment > 0.0
    assert 0.0 <= result.normalized_score <= 100.0
