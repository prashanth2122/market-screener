"""Sentiment scoring helpers for news-driven analytics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from market_screener.core.timezone import normalize_to_utc

POSITIVE_KEYWORDS = {
    "beat",
    "beats",
    "surge",
    "surges",
    "rally",
    "rallies",
    "upgrade",
    "upgrades",
    "strong",
    "growth",
    "profit",
    "profits",
    "record",
    "bullish",
    "outperform",
    "expands",
    "expansion",
    "gain",
    "gains",
    "positive",
}

NEGATIVE_KEYWORDS = {
    "miss",
    "misses",
    "drop",
    "drops",
    "slump",
    "falls",
    "fall",
    "downgrade",
    "downgrades",
    "weak",
    "loss",
    "losses",
    "fraud",
    "probe",
    "lawsuit",
    "lawsuits",
    "bearish",
    "warning",
    "risk",
    "negative",
}

TOKEN_PATTERN = re.compile(r"[a-zA-Z]+")


@dataclass(frozen=True)
class ArticleSentimentInput:
    """Article sentiment input with optional provider score and text context."""

    published_at: datetime
    provider_sentiment: float | None
    title: str | None
    description: str | None


@dataclass(frozen=True)
class ArticleSentimentDerivation:
    """Derived article sentiment value and scoring provenance."""

    score: float | None
    provider_score: float | None
    lexicon_score: float | None
    method: str


@dataclass(frozen=True)
class WeightedSentimentAggregateResult:
    """Weighted sentiment aggregate over a lookback window."""

    weighted_sentiment: float | None
    normalized_score: float | None
    article_count: int
    scored_article_count: int
    positive_articles: int
    negative_articles: int
    neutral_articles: int
    unavailable_articles: int


@dataclass(frozen=True)
class WeightedSentimentArticle:
    published_at: datetime
    score: float | None


def derive_article_sentiment(
    input_item: ArticleSentimentInput,
    *,
    provider_weight: float = 0.70,
) -> ArticleSentimentDerivation:
    """Derive final per-article sentiment using provider + lexicon blend."""

    provider_score = _clamp_sentiment(input_item.provider_sentiment)
    text = " ".join(
        part.strip() for part in (input_item.title or "", input_item.description or "") if part
    )
    lexicon_score = compute_lexicon_sentiment(text) if text else None

    if provider_score is not None and lexicon_score is not None:
        weight = _clamp(provider_weight, 0.0, 1.0)
        blended = (provider_score * weight) + (lexicon_score * (1.0 - weight))
        return ArticleSentimentDerivation(
            score=_clamp_sentiment(blended),
            provider_score=provider_score,
            lexicon_score=lexicon_score,
            method="blended",
        )
    if provider_score is not None:
        return ArticleSentimentDerivation(
            score=provider_score,
            provider_score=provider_score,
            lexicon_score=lexicon_score,
            method="provider",
        )
    if lexicon_score is not None:
        return ArticleSentimentDerivation(
            score=lexicon_score,
            provider_score=provider_score,
            lexicon_score=lexicon_score,
            method="lexicon",
        )
    return ArticleSentimentDerivation(
        score=None,
        provider_score=provider_score,
        lexicon_score=lexicon_score,
        method="unavailable",
    )


def compute_lexicon_sentiment(text: str) -> float | None:
    """Compute simple lexicon sentiment score in [-1, 1] from text tokens."""

    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    if not tokens:
        return None

    positive_count = sum(1 for token in tokens if token in POSITIVE_KEYWORDS)
    negative_count = sum(1 for token in tokens if token in NEGATIVE_KEYWORDS)
    total_hits = positive_count + negative_count
    if total_hits == 0:
        return None
    score = (positive_count - negative_count) / total_hits
    return _clamp_sentiment(score)


def compute_weighted_sentiment(
    articles: list[WeightedSentimentArticle],
    *,
    now_utc: datetime,
    lookback_hours: int,
    half_life_hours: int,
) -> WeightedSentimentAggregateResult:
    """Compute time-decayed weighted sentiment over lookback window."""

    reference_now = normalize_to_utc(now_utc)
    lookback = max(1, lookback_hours)
    half_life = max(1, half_life_hours)
    cutoff = reference_now - timedelta(hours=lookback)

    weighted_sum = 0.0
    weight_sum = 0.0
    article_count = 0
    scored_count = 0
    positive_count = 0
    negative_count = 0
    neutral_count = 0
    unavailable_count = 0

    for item in articles:
        published_at = normalize_to_utc(item.published_at)
        if published_at < cutoff or published_at > reference_now:
            continue
        article_count += 1
        if item.score is None:
            unavailable_count += 1
            continue

        score = _clamp_sentiment(item.score)
        if score is None:
            unavailable_count += 1
            continue

        scored_count += 1
        if score > 0.15:
            positive_count += 1
        elif score < -0.15:
            negative_count += 1
        else:
            neutral_count += 1

        age_hours = max(0.0, (reference_now - published_at).total_seconds() / 3600.0)
        weight = compute_time_decay_weight(age_hours=age_hours, half_life_hours=half_life)
        weighted_sum += score * weight
        weight_sum += weight

    if weight_sum <= 0:
        weighted_sentiment: float | None = None
        normalized_score: float | None = None
    else:
        weighted_sentiment = weighted_sum / weight_sum
        normalized_score = (weighted_sentiment + 1.0) * 50.0
        normalized_score = _clamp(normalized_score, 0.0, 100.0)

    return WeightedSentimentAggregateResult(
        weighted_sentiment=weighted_sentiment,
        normalized_score=normalized_score,
        article_count=article_count,
        scored_article_count=scored_count,
        positive_articles=positive_count,
        negative_articles=negative_count,
        neutral_articles=neutral_count,
        unavailable_articles=unavailable_count,
    )


def compute_time_decay_weight(*, age_hours: float, half_life_hours: int) -> float:
    """Compute exponential decay weight where age=half-life gives weight=0.5."""

    normalized_half_life = max(1, half_life_hours)
    if age_hours <= 0:
        return 1.0
    return 0.5 ** (age_hours / normalized_half_life)


def _clamp_sentiment(value: float | None) -> float | None:
    if value is None:
        return None
    return _clamp(float(value), -1.0, 1.0)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def main() -> None:
    """CLI entrypoint for sentiment scoring smoke check."""

    now = datetime.now(UTC)
    derivations = [
        derive_article_sentiment(
            ArticleSentimentInput(
                published_at=now - timedelta(hours=2),
                provider_sentiment=None,
                title="Company beats earnings and expands guidance",
                description=None,
            )
        ),
        derive_article_sentiment(
            ArticleSentimentInput(
                published_at=now - timedelta(hours=10),
                provider_sentiment=-0.4,
                title="Shares fall after weak outlook",
                description=None,
            )
        ),
    ]
    aggregate = compute_weighted_sentiment(
        [
            WeightedSentimentArticle(
                published_at=now - timedelta(hours=2), score=derivations[0].score
            ),
            WeightedSentimentArticle(
                published_at=now - timedelta(hours=10), score=derivations[1].score
            ),
        ],
        now_utc=now,
        lookback_hours=72,
        half_life_hours=24,
    )
    print(
        "sentiment_scoring:"
        f" ts={now.isoformat()}"
        f" weighted_sentiment={None if aggregate.weighted_sentiment is None else round(aggregate.weighted_sentiment, 4)}"
        f" normalized_score={None if aggregate.normalized_score is None else round(aggregate.normalized_score, 2)}"
        f" article_count={aggregate.article_count}"
        f" scored_article_count={aggregate.scored_article_count}"
    )


if __name__ == "__main__":
    main()
