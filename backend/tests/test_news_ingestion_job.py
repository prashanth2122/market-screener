"""Tests for news ingestion workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, NewsEvent
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.news_ingestion import NewsIngestionJob, run_news_ingestion


class _FakeNewsClient:
    def __init__(self, *, call_counter: dict[str, int] | None = None) -> None:
        self._call_counter = {} if call_counter is None else call_counter

    def __enter__(self) -> "_FakeNewsClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def get_news(
        self,
        symbol: str,
        *,
        limit: int,
        language: str,
        published_after: datetime | None = None,
    ) -> list[dict[str, Any]]:
        self._call_counter[symbol] = self._call_counter.get(symbol, 0) + 1
        assert limit == 2
        assert language == "en"
        assert published_after is not None
        if symbol == "AAPL":
            return [
                {
                    "published_at": "2026-04-23T08:00:00Z",
                    "title": "Apple expands AI roadmap",
                    "description": "Short summary",
                    "url": "https://example.com/apple-ai",
                    "language": "en",
                    "sentiment_score": 0.44,
                    "source": "example_wire",
                    "uuid": "article-aapl-1",
                    "entities": [{"symbol": "AAPL", "sentiment_score": 0.44}],
                }
            ]
        return []


class _FakeSession:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def add(self, job_row) -> None:
        self._store[job_row.run_id] = job_row

    def merge(self, job_row):
        self._store[job_row.run_id] = job_row
        return job_row

    def commit(self) -> None:
        return None


def _build_audit_trail(store: dict[str, Any]) -> JobAuditTrail:
    def _factory() -> _FakeSession:
        return _FakeSession(store)

    return JobAuditTrail(_factory)


def test_news_ingestion_job_writes_rows_for_active_assets() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        session.add_all(
            [
                Asset(
                    symbol="AAPL",
                    asset_type="equity",
                    exchange="US",
                    quote_currency="USD",
                    active=True,
                ),
                Asset(
                    symbol="BTC",
                    asset_type="crypto",
                    exchange="GLOBAL",
                    quote_currency="USD",
                    active=True,
                ),
                Asset(
                    symbol="MSFT",
                    asset_type="equity",
                    exchange="US",
                    quote_currency="USD",
                    active=False,
                ),
            ]
        )
        session.commit()

    job = NewsIngestionJob(
        session_local,
        lambda: _FakeNewsClient(),
        symbol_limit=10,
        limit_per_symbol=2,
        lookback_hours=72,
        language="en",
        source="marketaux_v1",
    )
    result = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))

    assert result.requested_assets == 2
    assert result.processed_assets == 2
    assert result.failed_assets == 0
    assert result.no_data_assets == 1
    assert result.articles_written == 1
    assert result.articles_skipped == 0

    with session_local() as session:
        row = session.scalar(select(NewsEvent))

    assert row is not None
    assert row.source == "example_wire"
    assert row.title == "Apple expands AI roadmap"
    assert str(row.published_at).startswith("2026-04-23")


def test_news_ingestion_job_skips_existing_rows_on_repeat_runs() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        session.add(
            Asset(
                symbol="AAPL",
                asset_type="equity",
                exchange="US",
                quote_currency="USD",
                active=True,
            )
        )
        session.commit()

    job = NewsIngestionJob(
        session_local,
        lambda: _FakeNewsClient(),
        symbol_limit=10,
        limit_per_symbol=2,
        lookback_hours=72,
        language="en",
        source="marketaux_v1",
    )

    first = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))
    second = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))

    assert first.articles_written == 1
    assert first.articles_skipped == 0
    assert second.articles_written == 0
    assert second.articles_skipped == 1


def test_news_ingestion_wrapper_skips_repeated_pull(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    NewsEvent.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        session.add(
            Asset(
                symbol="AAPL",
                asset_type="equity",
                exchange="US",
                quote_currency="USD",
                active=True,
            )
        )
        session.commit()

    call_counter: dict[str, int] = {}
    mock_client = _FakeNewsClient(call_counter=call_counter)
    monkeypatch.setattr(
        "market_screener.jobs.news_ingestion.MarketauxNewsClient.from_settings",
        lambda _settings: mock_client,
    )

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        marketaux_api_key="demo",
        news_ingestion_symbol_limit=10,
        news_ingestion_limit_per_symbol=2,
        news_ingestion_lookback_hours=72,
        news_ingestion_language="en",
        news_ingestion_source="marketaux_v1",
    )

    first = run_news_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )
    second = run_news_ingestion(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )

    assert first.idempotent_skip is False
    assert first.articles_written == 1
    assert second.idempotent_skip is True
    assert second.articles_written == 0
    assert call_counter == {"AAPL": 1}

    with session_local() as session:
        count = session.scalar(select(func.count()).select_from(NewsEvent))
    assert count == 1
