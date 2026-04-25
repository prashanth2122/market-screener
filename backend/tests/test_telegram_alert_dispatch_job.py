"""Tests for Telegram alert dispatch wrapper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.alerts.email_channel import EmailAlertDeliveryResult
from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, SignalHistory
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.telegram_alert_dispatch import run_telegram_alert_dispatch


class _FakeTelegramChannel:
    def __init__(self) -> None:
        self.calls = 0

    def send_alerts(self, alerts, *, now_utc=None) -> EmailAlertDeliveryResult:
        self.calls += 1
        return EmailAlertDeliveryResult(
            attempted_alerts=len(alerts),
            sent_alerts=len(alerts),
            failed_alerts=0,
        )


def test_run_telegram_alert_dispatch_wrapper_skips_repeated_hourly_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    with session_local() as session:
        asset = Asset(
            symbol="AAPL",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.flush()
        session.add(
            SignalHistory(
                asset_id=asset.id,
                as_of_ts=now - timedelta(hours=1),
                model_version="v1.0.0",
                signal="strong_buy",
                score=Decimal("85.00"),
                confidence=Decimal("0.80"),
                blocked_by_risk=False,
                reasons=["test_case"],
            )
        )
        session.commit()

    settings = Settings(
        alert_dispatch_symbol_limit=10,
        alert_dispatch_lookback_hours=24,
        alert_dispatch_signal_allowlist="strong_buy,buy",
        alert_dispatch_min_score=70.0,
        alert_max_per_day=5,
        alert_cooldown_minutes=60,
    )

    store: dict[str, Any] = {}

    class _FakeSession:
        def __init__(self, db_store: dict[str, Any]) -> None:
            self._store = db_store

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

    def _audit_session_factory() -> _FakeSession:
        return _FakeSession(store)

    audit_trail = JobAuditTrail(_audit_session_factory)
    channel = _FakeTelegramChannel()

    first = run_telegram_alert_dispatch(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        channel=channel,
        now_utc=now,
    )
    second = run_telegram_alert_dispatch(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        channel=channel,
        now_utc=now + timedelta(minutes=15),
    )

    assert first.idempotent_skip is False
    assert first.sent_alerts == 1
    assert second.idempotent_skip is True
    assert second.sent_alerts == 0
    assert channel.calls == 1
