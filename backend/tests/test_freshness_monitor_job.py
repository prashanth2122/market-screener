"""Tests for watchlist freshness monitoring workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, Price
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.freshness_monitor import (
    WatchlistFreshnessMonitorJob,
    parse_watchlist_symbols,
    run_watchlist_freshness_monitor,
)


class FakeSession:
    def __init__(self, store: dict[str, object]) -> None:
        self._store = store

    def __enter__(self) -> "FakeSession":
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


def _build_audit_trail(store: dict[str, object]) -> JobAuditTrail:
    def _factory() -> FakeSession:
        return FakeSession(store)

    return JobAuditTrail(_factory)


def test_parse_watchlist_symbols_normalizes_and_deduplicates() -> None:
    parsed = parse_watchlist_symbols(" aapl , btc, AAPL, , reliance ")
    assert parsed == ["AAPL", "BTC", "RELIANCE"]


def test_watchlist_freshness_monitor_classifies_symbol_states() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    with session_local() as session:
        aapl = Asset(
            symbol="AAPL",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        btc = Asset(
            symbol="BTC",
            asset_type="crypto",
            exchange="GLOBAL",
            quote_currency="USD",
            active=True,
        )
        nvda = Asset(
            symbol="NVDA",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        eth = Asset(
            symbol="ETH",
            asset_type="crypto",
            exchange="GLOBAL",
            quote_currency="USD",
            active=True,
        )
        session.add_all([aapl, btc, nvda, eth])
        session.flush()

        session.add_all(
            [
                Price(
                    asset_id=aapl.id,
                    ts=now - timedelta(minutes=2),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100.5"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=btc.id,
                    ts=now - timedelta(minutes=9),
                    open=Decimal("50000"),
                    high=Decimal("50100"),
                    low=Decimal("49900"),
                    close=Decimal("50050"),
                    volume=Decimal("10"),
                    source="coingecko",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=eth.id,
                    ts=now - timedelta(minutes=40),
                    open=Decimal("3000"),
                    high=Decimal("3010"),
                    low=Decimal("2990"),
                    close=Decimal("3002"),
                    volume=Decimal("10"),
                    source="coingecko",
                    ingest_id="seed",
                ),
            ]
        )
        session.commit()

    job = WatchlistFreshnessMonitorJob(
        session_local,
        watchlist_symbols=["AAPL", "BTC", "NVDA", "MSFT", "ETH"],
        target_age_minutes=5,
        max_age_minutes=15,
    )
    result = job.run(now_utc=now)

    assert result.requested_symbols == 5
    assert result.checked_symbols == 4
    assert result.unknown_symbols == 1
    assert result.fresh_symbols == 1
    assert result.warning_symbols == 1
    assert result.stale_symbols == 1
    assert result.missing_symbols == 1
    assert result.overall_success is False

    by_symbol = {status.symbol: status for status in result.symbol_statuses}
    assert by_symbol["AAPL"].status == "fresh"
    assert by_symbol["BTC"].status == "warning"
    assert by_symbol["BTC"].failure_reason == "target_breached"
    assert by_symbol["ETH"].status == "stale"
    assert by_symbol["ETH"].failure_reason == "max_age_breached"
    assert by_symbol["NVDA"].status == "missing"
    assert by_symbol["MSFT"].status == "unknown"


def test_watchlist_freshness_wrapper_uses_active_symbol_fallback_when_empty() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    Price.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    with session_local() as session:
        aapl = Asset(
            symbol="AAPL",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        btc = Asset(
            symbol="BTC",
            asset_type="crypto",
            exchange="GLOBAL",
            quote_currency="USD",
            active=True,
        )
        tsla = Asset(
            symbol="TSLA",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add_all([aapl, btc, tsla])
        session.flush()
        session.add_all(
            [
                Price(
                    asset_id=aapl.id,
                    ts=now - timedelta(minutes=1),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100.5"),
                    volume=Decimal("1000"),
                    source="finnhub",
                    ingest_id="seed",
                ),
                Price(
                    asset_id=btc.id,
                    ts=now - timedelta(minutes=20),
                    open=Decimal("50000"),
                    high=Decimal("50100"),
                    low=Decimal("49900"),
                    close=Decimal("50050"),
                    volume=Decimal("10"),
                    source="coingecko",
                    ingest_id="seed",
                ),
            ]
        )
        session.commit()

    settings = Settings(
        watchlist_symbols="",
        freshness_monitor_symbol_limit=2,
        freshness_monitor_target_age_minutes=5,
        max_stale_price_minutes=15,
    )
    store: dict[str, object] = {}
    audit_trail = _build_audit_trail(store)
    result = run_watchlist_freshness_monitor(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now,
    )

    assert result.requested_symbols == 2
    assert result.checked_symbols == 2
    assert result.unknown_symbols == 0
    assert result.fresh_symbols == 1
    assert result.warning_symbols == 0
    assert result.stale_symbols == 1
    assert result.missing_symbols == 0

    job_row = next(iter(store.values()))
    assert job_row.details["watchlist_source"] == "active_assets_fallback"
