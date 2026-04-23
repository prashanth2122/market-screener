"""Tests for fundamentals snapshot pull workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, FundamentalsSnapshot
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.fundamentals_snapshot import (
    FundamentalsSnapshotPullJob,
    run_fundamentals_snapshot_pull,
)


class _FakeFundamentalsClient:
    def __init__(self, *, call_counter: dict[str, int] | None = None) -> None:
        self._call_counter = {} if call_counter is None else call_counter

    def __enter__(self) -> "_FakeFundamentalsClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def get_income_statements(
        self,
        symbol: str,
        *,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self._call_counter["income"] = self._call_counter.get("income", 0) + 1
        assert symbol == "AAPL"
        assert period == "annual"
        assert limit == 1
        return [
            {
                "date": "2025-12-31",
                "fillingDate": "2026-02-05",
                "reportedCurrency": "USD",
                "revenue": 1000000,
                "grossProfit": 400000,
                "ebit": 250000,
                "netIncome": 200000,
                "eps": 2.5,
                "epsdiluted": 2.4,
                "weightedAverageShsOut": 100000,
            }
        ]

    def get_balance_sheet_statements(
        self,
        symbol: str,
        *,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self._call_counter["balance"] = self._call_counter.get("balance", 0) + 1
        assert symbol == "AAPL"
        assert period == "annual"
        assert limit == 1
        return [
            {
                "date": "2025-12-31",
                "totalAssets": 5000000,
                "totalLiabilities": 3000000,
                "totalCurrentAssets": 1500000,
                "totalCurrentLiabilities": 1000000,
                "longTermDebt": 700000,
                "retainedEarnings": 900000,
            }
        ]

    def get_cash_flow_statements(
        self,
        symbol: str,
        *,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self._call_counter["cash_flow"] = self._call_counter.get("cash_flow", 0) + 1
        assert symbol == "AAPL"
        assert period == "annual"
        assert limit == 1
        return [{"date": "2025-12-31", "operatingCashFlow": 260000}]

    def get_key_metrics(
        self,
        symbol: str,
        *,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self._call_counter["metrics"] = self._call_counter.get("metrics", 0) + 1
        assert symbol == "AAPL"
        assert period == "annual"
        assert limit == 1
        return [{"date": "2025-12-31", "sharesOutstanding": 110000, "marketCap": 7200000}]


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


def test_fundamentals_snapshot_job_writes_rows_for_active_equities() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
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
            ]
        )
        session.commit()

    job = FundamentalsSnapshotPullJob(
        session_local,
        lambda: _FakeFundamentalsClient(),
        symbol_limit=10,
        period_type="annual",
        limit_per_symbol=1,
        snapshot_source="fmp_v1",
    )
    result = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))

    assert result.requested_assets == 1
    assert result.processed_assets == 1
    assert result.failed_assets == 0
    assert result.no_data_assets == 0
    assert result.snapshots_written == 1
    assert result.snapshots_skipped == 0

    with session_local() as session:
        row = session.scalar(select(FundamentalsSnapshot))

    assert row is not None
    assert row.period_type == "annual"
    assert str(row.period_end) == "2025-12-31"
    assert float(row.revenue or 0) == 1000000.0
    assert float(row.market_cap or 0) == 7200000.0
    assert row.source == "fmp_v1"


def test_fundamentals_snapshot_job_skips_existing_rows_on_repeat_runs() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
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

    job = FundamentalsSnapshotPullJob(
        session_local,
        lambda: _FakeFundamentalsClient(),
        symbol_limit=10,
        period_type="annual",
        limit_per_symbol=1,
        snapshot_source="fmp_v1",
    )

    first = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))
    second = job.run(now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC))

    assert first.snapshots_written == 1
    assert first.snapshots_skipped == 0
    assert second.snapshots_written == 0
    assert second.snapshots_skipped == 1


def test_fundamentals_snapshot_wrapper_skips_repeated_pull(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    FundamentalsSnapshot.__table__.create(engine)
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
    mock_client = _FakeFundamentalsClient(call_counter=call_counter)
    monkeypatch.setattr(
        "market_screener.jobs.fundamentals_snapshot.FMPFundamentalsClient.from_settings",
        lambda _settings: mock_client,
    )

    store: dict[str, Any] = {}
    audit_trail = _build_audit_trail(store)
    settings = Settings(
        fmp_api_key="demo",
        fundamentals_snapshot_symbol_limit=10,
        fundamentals_snapshot_period_type="annual",
        fundamentals_snapshot_limit_per_symbol=1,
        fundamentals_snapshot_source="fmp_v1",
    )

    first = run_fundamentals_snapshot_pull(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )
    second = run_fundamentals_snapshot_pull(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )

    assert first.idempotent_skip is False
    assert first.snapshots_written == 1
    assert second.idempotent_skip is True
    assert second.snapshots_written == 0
    assert call_counter == {"income": 1, "balance": 1, "cash_flow": 1, "metrics": 1}

    with session_local() as session:
        count = session.scalar(select(func.count()).select_from(FundamentalsSnapshot))
    assert count == 1
