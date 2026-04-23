"""News article ingestion workflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, NewsEvent
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.idempotency import build_idempotency_key
from market_screener.providers.marketaux import MarketauxNewsClient

logger = logging.getLogger("market_screener.jobs.news_ingestion")


@dataclass(frozen=True)
class NewsIngestionResult:
    """Outcome summary for one news ingestion run."""

    requested_assets: int
    processed_assets: int
    failed_assets: int
    no_data_assets: int
    articles_written: int
    articles_skipped: int
    source: str
    idempotent_skip: bool = False


@dataclass(frozen=True)
class _NewsEventPayload:
    published_at: datetime
    source: str
    title: str
    description: str | None
    url: str | None
    language: str | None
    sentiment_score: Decimal | None
    details: dict[str, Any] | None


class NewsIngestionJob:
    """Fetch and persist recent news articles for active assets."""

    def __init__(
        self,
        session_factory: SessionFactory,
        news_client_factory: Any,
        *,
        symbol_limit: int,
        limit_per_symbol: int,
        lookback_hours: int,
        language: str,
        source: str,
    ) -> None:
        self._session_factory = session_factory
        self._news_client_factory = news_client_factory
        self._symbol_limit = max(1, symbol_limit)
        self._limit_per_symbol = max(1, limit_per_symbol)
        self._lookback_hours = max(1, lookback_hours)
        self._language = language.strip() or "en"
        self._source = source.strip() or "marketaux_v1"

    def run(self, *, now_utc: datetime | None = None) -> NewsIngestionResult:
        """Pull news articles and persist normalized rows."""

        reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
        published_after = reference_now - timedelta(hours=self._lookback_hours)
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
        no_data_assets = 0
        articles_written = 0
        articles_skipped = 0

        with self._news_client_factory() as client:
            for asset in assets:
                try:
                    raw_articles = client.get_news(
                        asset.symbol,
                        limit=self._limit_per_symbol,
                        language=self._language,
                        published_after=published_after,
                    )
                    parsed_articles = _normalize_news_rows(raw_articles, source=self._source)
                    processed_assets += 1
                except Exception:
                    failed_assets += 1
                    logger.exception(
                        "news_ingestion_asset_failed",
                        extra={
                            "asset_id": asset.id,
                            "symbol": asset.symbol,
                            "source": self._source,
                        },
                    )
                    continue

                if not parsed_articles:
                    no_data_assets += 1
                    continue

                written, skipped = _persist_news_events(
                    self._session_factory,
                    asset_id=asset.id,
                    rows=parsed_articles,
                )
                articles_written += written
                articles_skipped += skipped

        return NewsIngestionResult(
            requested_assets=len(assets),
            processed_assets=processed_assets,
            failed_assets=failed_assets,
            no_data_assets=no_data_assets,
            articles_written=articles_written,
            articles_skipped=articles_skipped,
            source=self._source,
        )


def run_news_ingestion(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> NewsIngestionResult:
    """Run news ingestion with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    window_anchor_hour = reference_now.strftime("%Y-%m-%dT%H")
    symbol_fingerprint = _active_symbol_fingerprint(resolved_session_factory)
    idempotency_key = build_idempotency_key(
        "news_ingestion",
        {
            "source": resolved_settings.news_ingestion_source,
            "symbol_limit": resolved_settings.news_ingestion_symbol_limit,
            "limit_per_symbol": resolved_settings.news_ingestion_limit_per_symbol,
            "lookback_hours": resolved_settings.news_ingestion_lookback_hours,
            "language": resolved_settings.news_ingestion_language,
            "window_anchor_hour": window_anchor_hour,
            "symbol_fingerprint": symbol_fingerprint,
        },
    )

    if resolved_audit.has_completed_run("news_ingestion", idempotency_key):
        return NewsIngestionResult(
            requested_assets=0,
            processed_assets=0,
            failed_assets=0,
            no_data_assets=0,
            articles_written=0,
            articles_skipped=0,
            source=resolved_settings.news_ingestion_source,
            idempotent_skip=True,
        )

    def _client_factory() -> MarketauxNewsClient:
        return MarketauxNewsClient.from_settings(resolved_settings)

    job = NewsIngestionJob(
        resolved_session_factory,
        _client_factory,
        symbol_limit=resolved_settings.news_ingestion_symbol_limit,
        limit_per_symbol=resolved_settings.news_ingestion_limit_per_symbol,
        lookback_hours=resolved_settings.news_ingestion_lookback_hours,
        language=resolved_settings.news_ingestion_language,
        source=resolved_settings.news_ingestion_source,
    )
    with resolved_audit.track_job_run(
        "news_ingestion",
        details={
            "provider": "marketaux",
            "source": resolved_settings.news_ingestion_source,
            "symbol_limit": resolved_settings.news_ingestion_symbol_limit,
            "limit_per_symbol": resolved_settings.news_ingestion_limit_per_symbol,
            "lookback_hours": resolved_settings.news_ingestion_lookback_hours,
            "language": resolved_settings.news_ingestion_language,
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
                "no_data_assets": result.no_data_assets,
                "articles_written": result.articles_written,
                "articles_skipped": result.articles_skipped,
                "source": result.source,
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


def _persist_news_events(
    session_factory: SessionFactory,
    *,
    asset_id: int,
    rows: list[_NewsEventPayload],
) -> tuple[int, int]:
    if not rows:
        return 0, 0

    with session_factory() as session:
        written = 0
        skipped = 0
        for item in rows:
            existing_id = session.scalar(
                select(NewsEvent.id).where(
                    NewsEvent.asset_id == asset_id,
                    NewsEvent.published_at == item.published_at,
                    NewsEvent.source == item.source,
                    NewsEvent.title == item.title,
                )
            )
            if existing_id is not None:
                skipped += 1
                continue
            session.add(
                NewsEvent(
                    asset_id=asset_id,
                    published_at=item.published_at,
                    source=item.source,
                    title=item.title,
                    description=item.description,
                    url=item.url,
                    language=item.language,
                    sentiment_score=item.sentiment_score,
                    event_type=None,
                    risk_flag=None,
                    details=item.details,
                )
            )
            written += 1
        session.commit()

    return written, skipped


def _normalize_news_rows(
    rows: list[dict[str, Any]],
    *,
    source: str,
) -> list[_NewsEventPayload]:
    normalized: list[_NewsEventPayload] = []
    for row in rows:
        published_at = _parse_datetime(
            _first_value(row, ("published_at", "publishedAt", "published", "datetime", "date"))
        )
        title = _to_optional_str(_first_value(row, ("title", "headline")))
        if published_at is None or title is None:
            continue

        normalized.append(
            _NewsEventPayload(
                published_at=published_at,
                source=_to_optional_str(_first_value(row, ("source", "news_source", "domain")))
                or source,
                title=title,
                description=_to_optional_str(
                    _first_value(row, ("description", "snippet", "summary"))
                ),
                url=_to_optional_str(_first_value(row, ("url", "link"))),
                language=_to_optional_str(_first_value(row, ("language",))),
                sentiment_score=_extract_sentiment_score(row),
                details={
                    "provider": "marketaux",
                    "uuid": _to_optional_str(_first_value(row, ("uuid", "id"))),
                    "entity_count": (
                        len(row.get("entities", []))
                        if isinstance(row.get("entities"), list)
                        else None
                    ),
                },
            )
        )
    return normalized


def _extract_sentiment_score(row: dict[str, Any]) -> Decimal | None:
    direct = _to_decimal(
        _first_value(
            row,
            ("sentiment_score", "sentiment", "overall_sentiment_score"),
        )
    )
    if direct is not None:
        return direct

    entities = row.get("entities")
    if not isinstance(entities, list):
        return None
    scores = [
        _to_decimal(entity.get("sentiment_score"))
        for entity in entities
        if isinstance(entity, dict)
    ]
    filtered = [score for score in scores if score is not None]
    if not filtered:
        return None
    return sum(filtered) / Decimal(len(filtered))


def _first_value(row: dict[str, Any] | None, keys: tuple[str, ...]) -> Any:
    if not row:
        return None
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return normalize_to_utc(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return normalize_to_utc(parsed)


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        text = str(value).strip()
        if not text:
            return None
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None


def main() -> None:
    """CLI entrypoint for manual news ingestion runs."""

    result = run_news_ingestion()
    logger.info(
        "news_ingestion_completed",
        extra={
            "requested_assets": result.requested_assets,
            "processed_assets": result.processed_assets,
            "failed_assets": result.failed_assets,
            "no_data_assets": result.no_data_assets,
            "articles_written": result.articles_written,
            "articles_skipped": result.articles_skipped,
            "source": result.source,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "news_ingestion:"
        f" requested_assets={result.requested_assets}"
        f" processed_assets={result.processed_assets}"
        f" failed_assets={result.failed_assets}"
        f" no_data_assets={result.no_data_assets}"
        f" articles_written={result.articles_written}"
        f" articles_skipped={result.articles_skipped}"
        f" source={result.source}"
        f" idempotent_skip={result.idempotent_skip}"
    )


if __name__ == "__main__":
    main()
