"""Event-risk tagging pipeline over recent news events."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from market_screener.core.event_risk import EventRiskInput, tag_event_risk
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, NewsEvent
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.idempotency import build_idempotency_key

logger = logging.getLogger("market_screener.jobs.event_risk_tagging")


@dataclass(frozen=True)
class AssetEventRiskStatus:
    """Per-asset event-risk tagging status."""

    symbol: str
    article_count: int
    high_risk_articles: int
    tagged_articles: int
    sentiment_only_risk_articles: int


@dataclass(frozen=True)
class EventRiskTaggingResult:
    """Outcome summary for one event-risk tagging run."""

    requested_assets: int
    processed_assets: int
    failed_assets: int
    assets_without_articles: int
    articles_scanned: int
    articles_updated: int
    high_risk_articles: int
    lookback_hours: int
    source_filter: str | None
    negative_sentiment_threshold: float
    statuses: list[AssetEventRiskStatus]
    idempotent_skip: bool = False


class EventRiskTaggingJob:
    """Apply event-risk tagging rules to recent news events."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        symbol_limit: int,
        lookback_hours: int,
        source_filter: str | None,
        negative_sentiment_threshold: float,
    ) -> None:
        self._session_factory = session_factory
        self._symbol_limit = max(1, symbol_limit)
        self._lookback_hours = max(1, lookback_hours)
        normalized_source = (source_filter or "").strip()
        self._source_filter = normalized_source or None
        self._negative_sentiment_threshold = float(negative_sentiment_threshold)

    def run(self, *, now_utc: datetime | None = None) -> EventRiskTaggingResult:
        """Run event-risk tagging over the configured asset universe."""

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
        articles_scanned = 0
        articles_updated = 0
        high_risk_articles = 0
        statuses: list[AssetEventRiskStatus] = []

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
                            AssetEventRiskStatus(
                                symbol=asset.symbol,
                                article_count=0,
                                high_risk_articles=0,
                                tagged_articles=0,
                                sentiment_only_risk_articles=0,
                            )
                        )
                        processed_assets += 1
                        continue

                    tagged_count = 0
                    high_risk_count = 0
                    sentiment_only_count = 0
                    for row in rows:
                        articles_scanned += 1
                        risk_result = tag_event_risk(
                            EventRiskInput(
                                title=row.title,
                                description=row.description,
                                sentiment_score=_to_float(row.sentiment_score),
                            ),
                            negative_sentiment_threshold=self._negative_sentiment_threshold,
                        )

                        if risk_result.event_type is not None:
                            tagged_count += 1
                        if risk_result.risk_flag:
                            high_risk_count += 1
                            high_risk_articles += 1
                        if (
                            risk_result.event_type == "sentiment_shock"
                            and risk_result.risk_flag
                            and not risk_result.matched_keywords
                        ):
                            sentiment_only_count += 1

                        details = dict(row.details or {})
                        details["event_risk_rule_hits"] = risk_result.rule_hits
                        details["event_risk_keywords"] = risk_result.matched_keywords
                        details["event_risk_sentiment_triggered"] = risk_result.sentiment_risk
                        details["event_risk_tagged_at"] = reference_now.isoformat()

                        changed = (
                            row.event_type != risk_result.event_type
                            or row.risk_flag != risk_result.risk_flag
                            or row.details != details
                        )
                        if changed:
                            row.event_type = risk_result.event_type
                            row.risk_flag = risk_result.risk_flag
                            row.details = details
                            articles_updated += 1

                    statuses.append(
                        AssetEventRiskStatus(
                            symbol=asset.symbol,
                            article_count=len(rows),
                            high_risk_articles=high_risk_count,
                            tagged_articles=tagged_count,
                            sentiment_only_risk_articles=sentiment_only_count,
                        )
                    )
                    processed_assets += 1
                except Exception:
                    failed_assets += 1
                    logger.exception(
                        "event_risk_tagging_asset_failed",
                        extra={"asset_id": asset.id, "symbol": asset.symbol},
                    )
                    continue

            session.commit()

        return EventRiskTaggingResult(
            requested_assets=len(assets),
            processed_assets=processed_assets,
            failed_assets=failed_assets,
            assets_without_articles=assets_without_articles,
            articles_scanned=articles_scanned,
            articles_updated=articles_updated,
            high_risk_articles=high_risk_articles,
            lookback_hours=self._lookback_hours,
            source_filter=self._source_filter,
            negative_sentiment_threshold=self._negative_sentiment_threshold,
            statuses=statuses,
        )


def run_event_risk_tagging(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> EventRiskTaggingResult:
    """Run event-risk tagging with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    window_anchor_hour = reference_now.strftime("%Y-%m-%dT%H")
    symbol_fingerprint = _active_symbol_fingerprint(resolved_session_factory)
    idempotency_key = build_idempotency_key(
        "event_risk_tagging",
        {
            "symbol_limit": resolved_settings.event_risk_symbol_limit,
            "lookback_hours": resolved_settings.event_risk_lookback_hours,
            "source_filter": resolved_settings.event_risk_source_filter,
            "negative_sentiment_threshold": resolved_settings.event_risk_negative_sentiment_threshold,
            "window_anchor_hour": window_anchor_hour,
            "symbol_fingerprint": symbol_fingerprint,
        },
    )

    if resolved_audit.has_completed_run("event_risk_tagging", idempotency_key):
        return EventRiskTaggingResult(
            requested_assets=0,
            processed_assets=0,
            failed_assets=0,
            assets_without_articles=0,
            articles_scanned=0,
            articles_updated=0,
            high_risk_articles=0,
            lookback_hours=resolved_settings.event_risk_lookback_hours,
            source_filter=(resolved_settings.event_risk_source_filter or "").strip() or None,
            negative_sentiment_threshold=resolved_settings.event_risk_negative_sentiment_threshold,
            statuses=[],
            idempotent_skip=True,
        )

    job = EventRiskTaggingJob(
        resolved_session_factory,
        symbol_limit=resolved_settings.event_risk_symbol_limit,
        lookback_hours=resolved_settings.event_risk_lookback_hours,
        source_filter=resolved_settings.event_risk_source_filter,
        negative_sentiment_threshold=resolved_settings.event_risk_negative_sentiment_threshold,
    )
    with resolved_audit.track_job_run(
        "event_risk_tagging",
        details={
            "symbol_limit": resolved_settings.event_risk_symbol_limit,
            "lookback_hours": resolved_settings.event_risk_lookback_hours,
            "source_filter": resolved_settings.event_risk_source_filter,
            "negative_sentiment_threshold": resolved_settings.event_risk_negative_sentiment_threshold,
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
                "articles_scanned": result.articles_scanned,
                "articles_updated": result.articles_updated,
                "high_risk_articles": result.high_risk_articles,
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


def main() -> None:
    """CLI entrypoint for manual event-risk tagging runs."""

    result = run_event_risk_tagging()
    logger.info(
        "event_risk_tagging_completed",
        extra={
            "requested_assets": result.requested_assets,
            "processed_assets": result.processed_assets,
            "failed_assets": result.failed_assets,
            "assets_without_articles": result.assets_without_articles,
            "articles_scanned": result.articles_scanned,
            "articles_updated": result.articles_updated,
            "high_risk_articles": result.high_risk_articles,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "event_risk_tagging:"
        f" requested_assets={result.requested_assets}"
        f" processed_assets={result.processed_assets}"
        f" failed_assets={result.failed_assets}"
        f" assets_without_articles={result.assets_without_articles}"
        f" articles_scanned={result.articles_scanned}"
        f" articles_updated={result.articles_updated}"
        f" high_risk_articles={result.high_risk_articles}"
        f" idempotent_skip={result.idempotent_skip}"
    )


if __name__ == "__main__":
    main()
