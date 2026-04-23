"""Sentiment scoring pipeline over recent news events."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from market_screener.core.sentiment import (
    ArticleSentimentInput,
    compute_weighted_sentiment,
    derive_article_sentiment,
    WeightedSentimentArticle,
)
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, NewsEvent
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.idempotency import build_idempotency_key

logger = logging.getLogger("market_screener.jobs.sentiment_scoring")


@dataclass(frozen=True)
class AssetSentimentStatus:
    """Per-asset sentiment scoring status."""

    symbol: str
    article_count: int
    scored_article_count: int
    weighted_sentiment: float | None
    normalized_score: float | None
    positive_articles: int
    negative_articles: int
    neutral_articles: int
    unavailable_articles: int


@dataclass(frozen=True)
class SentimentScoringResult:
    """Outcome summary for one sentiment scoring run."""

    requested_assets: int
    processed_assets: int
    failed_assets: int
    assets_without_articles: int
    updated_articles: int
    lookback_hours: int
    half_life_hours: int
    source_filter: str | None
    statuses: list[AssetSentimentStatus]
    idempotent_skip: bool = False


class SentimentScoringJob:
    """Compute weighted sentiment signals from recent news events."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        symbol_limit: int,
        lookback_hours: int,
        half_life_hours: int,
        source_filter: str | None,
    ) -> None:
        self._session_factory = session_factory
        self._symbol_limit = max(1, symbol_limit)
        self._lookback_hours = max(1, lookback_hours)
        self._half_life_hours = max(1, half_life_hours)
        normalized_source = (source_filter or "").strip()
        self._source_filter = normalized_source or None

    def run(self, *, now_utc: datetime | None = None) -> SentimentScoringResult:
        """Run sentiment scoring over the configured asset universe."""

        reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
        cutoff = reference_now - timedelta(hours=self._lookback_hours)
        with self._session_factory() as session:
            assets = list(
                session.scalars(
                    select(Asset)
                    .where(Asset.active.is_(True))
                    .order_by(Asset.symbol.asc())
                    .limit(self._symbol_limit)
                ).all()
            )

        processed_assets = 0
        failed_assets = 0
        assets_without_articles = 0
        updated_articles = 0
        statuses: list[AssetSentimentStatus] = []

        with self._session_factory() as session:
            for asset in assets:
                try:
                    news_query = select(NewsEvent).where(
                        NewsEvent.asset_id == asset.id,
                        NewsEvent.published_at >= cutoff,
                    )
                    if self._source_filter:
                        news_query = news_query.where(NewsEvent.source == self._source_filter)
                    news_query = news_query.order_by(NewsEvent.published_at.desc())
                    rows = list(session.scalars(news_query).all())

                    if not rows:
                        assets_without_articles += 1
                        statuses.append(
                            AssetSentimentStatus(
                                symbol=asset.symbol,
                                article_count=0,
                                scored_article_count=0,
                                weighted_sentiment=None,
                                normalized_score=None,
                                positive_articles=0,
                                negative_articles=0,
                                neutral_articles=0,
                                unavailable_articles=0,
                            )
                        )
                        processed_assets += 1
                        continue

                    weighted_inputs: list[WeightedSentimentArticle] = []
                    for row in rows:
                        provider_score = _to_float(row.sentiment_score)
                        derived = derive_article_sentiment(
                            ArticleSentimentInput(
                                published_at=normalize_to_utc(row.published_at),
                                provider_sentiment=provider_score,
                                title=row.title,
                                description=row.description,
                            )
                        )
                        weighted_inputs.append(
                            WeightedSentimentArticle(
                                published_at=normalize_to_utc(row.published_at),
                                score=derived.score,
                            )
                        )

                        if row.sentiment_score is None and derived.score is not None:
                            row.sentiment_score = _to_decimal(derived.score)
                            details = dict(row.details or {})
                            details["sentiment_method"] = derived.method
                            details["sentiment_updated_at"] = reference_now.isoformat()
                            row.details = details
                            updated_articles += 1

                    aggregate = compute_weighted_sentiment(
                        weighted_inputs,
                        now_utc=reference_now,
                        lookback_hours=self._lookback_hours,
                        half_life_hours=self._half_life_hours,
                    )
                    statuses.append(
                        AssetSentimentStatus(
                            symbol=asset.symbol,
                            article_count=aggregate.article_count,
                            scored_article_count=aggregate.scored_article_count,
                            weighted_sentiment=aggregate.weighted_sentiment,
                            normalized_score=aggregate.normalized_score,
                            positive_articles=aggregate.positive_articles,
                            negative_articles=aggregate.negative_articles,
                            neutral_articles=aggregate.neutral_articles,
                            unavailable_articles=aggregate.unavailable_articles,
                        )
                    )
                    processed_assets += 1
                except Exception:
                    failed_assets += 1
                    logger.exception(
                        "sentiment_scoring_asset_failed",
                        extra={"asset_id": asset.id, "symbol": asset.symbol},
                    )
                    continue

            session.commit()

        return SentimentScoringResult(
            requested_assets=len(assets),
            processed_assets=processed_assets,
            failed_assets=failed_assets,
            assets_without_articles=assets_without_articles,
            updated_articles=updated_articles,
            lookback_hours=self._lookback_hours,
            half_life_hours=self._half_life_hours,
            source_filter=self._source_filter,
            statuses=statuses,
        )


def run_sentiment_scoring(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> SentimentScoringResult:
    """Run sentiment scoring with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    window_anchor_hour = reference_now.strftime("%Y-%m-%dT%H")
    symbol_fingerprint = _active_symbol_fingerprint(resolved_session_factory)
    idempotency_key = build_idempotency_key(
        "sentiment_scoring",
        {
            "symbol_limit": resolved_settings.sentiment_pipeline_symbol_limit,
            "lookback_hours": resolved_settings.sentiment_pipeline_lookback_hours,
            "half_life_hours": resolved_settings.sentiment_pipeline_half_life_hours,
            "source_filter": resolved_settings.sentiment_pipeline_source_filter,
            "window_anchor_hour": window_anchor_hour,
            "symbol_fingerprint": symbol_fingerprint,
        },
    )

    if resolved_audit.has_completed_run("sentiment_scoring", idempotency_key):
        return SentimentScoringResult(
            requested_assets=0,
            processed_assets=0,
            failed_assets=0,
            assets_without_articles=0,
            updated_articles=0,
            lookback_hours=resolved_settings.sentiment_pipeline_lookback_hours,
            half_life_hours=resolved_settings.sentiment_pipeline_half_life_hours,
            source_filter=(resolved_settings.sentiment_pipeline_source_filter or "").strip()
            or None,
            statuses=[],
            idempotent_skip=True,
        )

    job = SentimentScoringJob(
        resolved_session_factory,
        symbol_limit=resolved_settings.sentiment_pipeline_symbol_limit,
        lookback_hours=resolved_settings.sentiment_pipeline_lookback_hours,
        half_life_hours=resolved_settings.sentiment_pipeline_half_life_hours,
        source_filter=resolved_settings.sentiment_pipeline_source_filter,
    )
    with resolved_audit.track_job_run(
        "sentiment_scoring",
        details={
            "symbol_limit": resolved_settings.sentiment_pipeline_symbol_limit,
            "lookback_hours": resolved_settings.sentiment_pipeline_lookback_hours,
            "half_life_hours": resolved_settings.sentiment_pipeline_half_life_hours,
            "source_filter": resolved_settings.sentiment_pipeline_source_filter,
            "window_anchor_hour": window_anchor_hour,
            "symbol_fingerprint": symbol_fingerprint,
            "idempotency_key": idempotency_key,
            "idempotency_hit": False,
        },
        idempotency_key=idempotency_key,
    ) as run_handle:
        result = job.run(now_utc=reference_now)
        run_handle.add_details(
            {
                "requested_assets": result.requested_assets,
                "processed_assets": result.processed_assets,
                "failed_assets": result.failed_assets,
                "assets_without_articles": result.assets_without_articles,
                "updated_articles": result.updated_articles,
                "idempotent_skip": False,
            }
        )
        return result


def _active_symbol_fingerprint(session_factory: SessionFactory) -> str:
    with session_factory() as session:
        symbols = sorted(session.scalars(select(Asset.symbol).where(Asset.active.is_(True))).all())
    if not symbols:
        return "none"
    return "|".join(symbols)


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(f"{value:.4f}")
    except (InvalidOperation, ValueError):
        return None


def main() -> None:
    """CLI entrypoint for manual sentiment scoring runs."""

    result = run_sentiment_scoring()
    logger.info(
        "sentiment_scoring_completed",
        extra={
            "requested_assets": result.requested_assets,
            "processed_assets": result.processed_assets,
            "failed_assets": result.failed_assets,
            "assets_without_articles": result.assets_without_articles,
            "updated_articles": result.updated_articles,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "sentiment_scoring:"
        f" requested_assets={result.requested_assets}"
        f" processed_assets={result.processed_assets}"
        f" failed_assets={result.failed_assets}"
        f" assets_without_articles={result.assets_without_articles}"
        f" updated_articles={result.updated_articles}"
        f" idempotent_skip={result.idempotent_skip}"
    )


if __name__ == "__main__":
    main()
