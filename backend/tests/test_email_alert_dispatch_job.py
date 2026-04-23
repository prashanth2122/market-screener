"""Tests for email alert dispatch workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from market_screener.alerts.email_channel import EmailAlert, EmailAlertDeliveryResult
from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, SignalHistory
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.email_alert_dispatch import (
    EmailAlertDispatchJob,
    run_email_alert_dispatch,
)


class _FakeEmailChannel:
    def __init__(
        self,
        *,
        skipped_reason: str | None = None,
        fail: bool = False,
    ) -> None:
        self.skipped_reason = skipped_reason
        self.fail = fail
        self.alerts: list[EmailAlert] = []

    def send_alerts(self, alerts: list[EmailAlert], *, now_utc=None) -> EmailAlertDeliveryResult:
        self.alerts = list(alerts)
        if self.skipped_reason is not None:
            return EmailAlertDeliveryResult(
                attempted_alerts=len(alerts),
                sent_alerts=0,
                failed_alerts=0,
                skipped_reason=self.skipped_reason,
            )
        if self.fail:
            return EmailAlertDeliveryResult(
                attempted_alerts=len(alerts),
                sent_alerts=0,
                failed_alerts=len(alerts),
                error_message="smtp failure",
            )
        return EmailAlertDeliveryResult(
            attempted_alerts=len(alerts),
            sent_alerts=len(alerts),
            failed_alerts=0,
        )


def _seed_signal(
    session_local,
    *,
    symbol: str,
    signal: str,
    score: Decimal,
    blocked_by_risk: bool,
    as_of_ts: datetime,
) -> None:
    with session_local() as session:
        asset = Asset(
            symbol=symbol,
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
                as_of_ts=as_of_ts,
                model_version="v1.0.0",
                signal=signal,
                score=score,
                confidence=Decimal("0.80"),
                blocked_by_risk=blocked_by_risk,
                reasons=["test_case"],
            )
        )
        session.commit()


def test_email_alert_dispatch_job_sends_only_actionable_candidates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    _seed_signal(
        session_local,
        symbol="AAPL",
        signal="strong_buy",
        score=Decimal("84.50"),
        blocked_by_risk=False,
        as_of_ts=now - timedelta(hours=1),
    )
    _seed_signal(
        session_local,
        symbol="MSFT",
        signal="watch",
        score=Decimal("76.00"),
        blocked_by_risk=False,
        as_of_ts=now - timedelta(hours=1),
    )
    _seed_signal(
        session_local,
        symbol="TSLA",
        signal="buy",
        score=Decimal("68.00"),
        blocked_by_risk=False,
        as_of_ts=now - timedelta(hours=1),
    )
    _seed_signal(
        session_local,
        symbol="GOOGL",
        signal="buy",
        score=Decimal("75.00"),
        blocked_by_risk=True,
        as_of_ts=now - timedelta(hours=1),
    )

    channel = _FakeEmailChannel()
    job = EmailAlertDispatchJob(
        session_local,
        channel=channel,
        symbol_limit=10,
        lookback_hours=24,
        min_score=70.0,
        allowed_signals={"strong_buy", "buy"},
        model_version="v1.0.0",
        max_per_day=5,
        cooldown_minutes=60,
    )
    result = job.run(now_utc=now)

    assert result.evaluated_assets == 4
    assert result.candidate_alerts == 1
    assert result.sent_alerts == 1
    assert result.failed_alerts == 0
    assert result.skipped_signal_not_allowed == 1
    assert result.skipped_below_threshold == 1
    assert result.skipped_blocked_risk == 1
    assert [alert.symbol for alert in channel.alerts] == ["AAPL"]


def test_email_alert_dispatch_job_applies_cooldown_and_daily_limit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    _seed_signal(
        session_local,
        symbol="AAPL",
        signal="buy",
        score=Decimal("80.00"),
        blocked_by_risk=False,
        as_of_ts=now - timedelta(hours=1),
    )
    _seed_signal(
        session_local,
        symbol="MSFT",
        signal="buy",
        score=Decimal("81.00"),
        blocked_by_risk=False,
        as_of_ts=now - timedelta(hours=1),
    )
    _seed_signal(
        session_local,
        symbol="NVDA",
        signal="buy",
        score=Decimal("79.00"),
        blocked_by_risk=False,
        as_of_ts=now - timedelta(hours=1),
    )

    channel = _FakeEmailChannel()

    def _mock_recent_sends(
        _session, _now: datetime, _cooldown_minutes: int
    ) -> tuple[int, set[str]]:
        return 1, {"AAPL"}

    job = EmailAlertDispatchJob(
        session_local,
        channel=channel,
        symbol_limit=10,
        lookback_hours=24,
        min_score=70.0,
        allowed_signals={"buy"},
        model_version="v1.0.0",
        max_per_day=2,
        cooldown_minutes=60,
        recent_send_context_loader=_mock_recent_sends,
    )
    result = job.run(now_utc=now)

    assert result.sent_alerts == 1
    assert result.skipped_cooldown == 1
    assert result.skipped_daily_limit == 1
    assert [alert.symbol for alert in channel.alerts] == ["MSFT"]


def test_run_email_alert_dispatch_wrapper_skips_repeated_hourly_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    _seed_signal(
        session_local,
        symbol="AAPL",
        signal="strong_buy",
        score=Decimal("85.00"),
        blocked_by_risk=False,
        as_of_ts=now - timedelta(hours=1),
    )

    settings = Settings(
        alert_dispatch_symbol_limit=10,
        alert_dispatch_lookback_hours=24,
        alert_dispatch_signal_allowlist="strong_buy,buy",
        alert_dispatch_min_score=70.0,
        alert_max_per_day=5,
        alert_cooldown_minutes=60,
    )
    channel = _FakeEmailChannel()
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

    first = run_email_alert_dispatch(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        channel=channel,
        now_utc=now,
    )
    second = run_email_alert_dispatch(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        channel=channel,
        now_utc=now + timedelta(minutes=20),
    )

    assert first.idempotent_skip is False
    assert first.sent_alerts == 1
    assert second.idempotent_skip is True
    assert second.sent_alerts == 0
