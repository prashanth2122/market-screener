"""Core ORM entities for the initial schema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from market_screener.db.base import Base

_JSON_DETAILS = JSON().with_variant(JSONB, "postgresql")


class Asset(Base):
    """Tracked market instrument metadata."""

    __tablename__ = "assets"
    __table_args__ = (
        Index(
            "ix_assets_active_type_exchange_quote",
            "active",
            "asset_type",
            "exchange",
            "quote_currency",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    base_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    quote_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Watchlist(Base):
    """User-managed watchlist metadata."""

    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("name", name="uq_watchlists_name"),
        Index("ix_watchlists_active_name", "active", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WatchlistItem(Base):
    """Asset membership records for watchlists."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "asset_id", name="uq_watchlist_items_watchlist_asset"),
        Index("ix_watchlist_items_watchlist_added", "watchlist_id", "added_at"),
        Index("ix_watchlist_items_asset", "asset_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Price(Base):
    """OHLCV price snapshots with provider provenance."""

    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("asset_id", "ts", "source", name="uq_prices_asset_ts_source"),
        Index("ix_prices_asset_ts", "asset_id", "ts"),
        Index("ix_prices_asset_source_ts", "asset_id", "source", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    ingest_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Job(Base):
    """Operational job execution log."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_name_started_at", "job_name", "started_at"),
        Index("ix_jobs_name_idempotency", "job_name", "idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(_JSON_DETAILS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProviderHealth(Base):
    """Provider reliability and latency telemetry."""

    __tablename__ = "provider_health"
    __table_args__ = (
        UniqueConstraint("provider_name", "ts", name="uq_provider_health_provider_ts"),
        Index("ix_provider_health_provider_ts", "provider_name", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    success_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    quota_remaining: Mapped[int | None] = mapped_column(nullable=True)
    error_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    details: Mapped[dict[str, Any] | None] = mapped_column(_JSON_DETAILS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IngestionFailure(Base):
    """Persisted ingestion failures for retry workflow."""

    __tablename__ = "ingestion_failures"
    __table_args__ = (
        UniqueConstraint("failure_key", name="uq_ingestion_failures_failure_key"),
        Index("ix_ingestion_failures_status_next_retry", "status", "next_retry_at"),
        Index("ix_ingestion_failures_job_symbol", "job_name", "asset_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    failure_key: Mapped[str] = mapped_column(String(160), nullable=False)
    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pending'")
    )
    attempt_count: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DeadLetterPayload(Base):
    """Persisted non-retryable ingestion payload failures (dead-letter queue)."""

    __tablename__ = "dead_letter_payloads"
    __table_args__ = (
        UniqueConstraint("dead_letter_key", name="uq_dead_letter_payloads_dead_letter_key"),
        Index("ix_dead_letter_payloads_job_symbol", "job_name", "asset_symbol"),
        Index("ix_dead_letter_payloads_last_seen", "last_seen_at"),
        Index("ix_dead_letter_payloads_provider_type", "provider_name", "payload_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dead_letter_key: Mapped[str] = mapped_column(String(160), nullable=False)
    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_type: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    seen_count: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IndicatorSnapshot(Base):
    """Persisted technical-indicator snapshots derived from OHLCV prices."""

    __tablename__ = "indicators_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "ts",
            "source",
            name="uq_indicators_snapshot_asset_ts_source",
        ),
        Index("ix_indicators_snapshot_asset_ts", "asset_id", "ts"),
        Index("ix_indicators_snapshot_asset_source_ts", "asset_id", "source", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ma50: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    ma200: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    rsi14: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    macd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    macd_signal: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    atr14: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    bb_upper: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    bb_lower: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FundamentalsSnapshot(Base):
    """Persisted fundamentals snapshots for scoring and quality models."""

    __tablename__ = "fundamentals_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "period_type",
            "period_end",
            "source",
            name="uq_fundamentals_snapshot_asset_period_source",
        ),
        Index("ix_fundamentals_snapshot_asset_as_of", "asset_id", "as_of_ts"),
        Index(
            "ix_fundamentals_snapshot_asset_period",
            "asset_id",
            "period_type",
            "period_end",
        ),
        Index(
            "ix_fundamentals_snapshot_asset_source_period",
            "asset_id",
            "source",
            "period_end",
            "as_of_ts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    as_of_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

    revenue: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    gross_profit: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    ebit: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    operating_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)

    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    total_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    long_term_debt: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    retained_earnings: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    shares_outstanding: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)

    eps_basic: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    eps_diluted: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NewsEvent(Base):
    """Persisted news articles/events used by sentiment and risk pipelines."""

    __tablename__ = "news_events"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "published_at",
            "source",
            "title",
            name="uq_news_events_asset_published_source_title",
        ),
        Index("ix_news_events_asset_published", "asset_id", "published_at"),
        Index("ix_news_events_asset_source_published", "asset_id", "source", "published_at"),
        Index("ix_news_events_source_published", "source", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_flag: Mapped[bool | None] = mapped_column(nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScoreHistory(Base):
    """Persisted composite score history per asset and model version."""

    __tablename__ = "score_history"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "as_of_ts",
            "model_version",
            name="uq_score_history_asset_asof_model",
        ),
        Index("ix_score_history_asset_asof", "asset_id", "as_of_ts"),
        Index("ix_score_history_asset_model_asof", "asset_id", "model_version", "as_of_ts"),
        Index("ix_score_history_model_asof", "model_version", "as_of_ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    as_of_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    composite_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    technical_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    fundamental_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    sentiment_risk_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SignalHistory(Base):
    """Persisted signal history per asset and model version."""

    __tablename__ = "signal_history"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "as_of_ts",
            "model_version",
            name="uq_signal_history_asset_asof_model",
        ),
        Index("ix_signal_history_asset_asof", "asset_id", "as_of_ts"),
        Index("ix_signal_history_model_asset_asof", "model_version", "asset_id", "as_of_ts"),
        Index("ix_signal_history_asset_model_asof", "asset_id", "model_version", "as_of_ts"),
        Index("ix_signal_history_signal_asof", "signal", "as_of_ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    as_of_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    signal: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    blocked_by_risk: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("false"),
    )
    reasons: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
