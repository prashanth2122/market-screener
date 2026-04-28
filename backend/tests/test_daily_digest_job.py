"""Tests for daily digest job (Day 95)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_screener.core.settings import Settings
from market_screener.db.models.core import Asset, Job, SignalHistory
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.daily_digest import DailyDigestJob, run_daily_digest


class _FakeChannel:
    def __init__(self) -> None:
        self.calls = 0
        self.alerts = []

    def send_alerts(self, alerts, *, now_utc=None):
        self.calls += 1
        self.alerts = list(alerts)
        return type(
            "R",
            (),
            {
                "attempted_alerts": len(alerts),
                "sent_alerts": len(alerts),
                "failed_alerts": 0,
                "skipped_reason": None,
                "error_message": None,
            },
        )()


def _seed_asset_with_signal(
    session_local, *, symbol: str, signal: str, score: Decimal, now: datetime
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
                as_of_ts=now - timedelta(hours=1),
                model_version="v1.0.1",
                signal=signal,
                score=score,
                confidence=Decimal("0.80"),
                blocked_by_risk=False,
                reasons=["seeded"],
            )
        )
        session.commit()


def test_daily_digest_job_selects_candidates_and_sends_digest() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    _seed_asset_with_signal(
        session_local, symbol="AAPL", signal="buy", score=Decimal("80.0"), now=now
    )
    _seed_asset_with_signal(
        session_local, symbol="MSFT", signal="watch", score=Decimal("90.0"), now=now
    )

    channel = _FakeChannel()
    job = DailyDigestJob(
        session_local,
        channel=channel,
        dispatch_job_name="telegram_daily_digest",
        symbol_limit=10,
        lookback_hours=24,
        min_score=70.0,
        allowed_signals={"buy"},
        model_version="v1.0.1",
        include_blocked_by_risk=False,
    )
    result = job.run(now_utc=now)

    assert result.candidates == 1
    assert result.sent == 1
    assert channel.calls == 1
    assert [alert.symbol for alert in channel.alerts] == ["AAPL"]


def test_run_daily_digest_is_idempotent_per_day(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    Job.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    _seed_asset_with_signal(
        session_local, symbol="AAPL", signal="buy", score=Decimal("80.0"), now=now
    )

    settings = Settings(
        daily_digest_telegram_enabled=True,
        daily_digest_email_enabled=False,
        daily_digest_symbol_limit=10,
        daily_digest_lookback_hours=24,
        daily_digest_signal_allowlist="buy",
        daily_digest_min_score=70.0,
        alert_dispatch_signal_allowlist="buy",
        alert_dispatch_min_score=70.0,
    )

    audit_trail = JobAuditTrail(session_local)

    first = run_daily_digest(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now,
    )
    second = run_daily_digest(
        settings=settings,
        session_factory=session_local,
        audit_trail=audit_trail,
        now_utc=now + timedelta(hours=2),
    )

    assert first["channels"]["telegram"]["idempotent_skip"] is False
    assert second["channels"]["telegram"]["idempotent_skip"] is True
