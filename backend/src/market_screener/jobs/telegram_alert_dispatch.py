"""Telegram alert dispatch job using actionable signal selection workflow."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from market_screener.alerts.telegram_channel import (
    TelegramAlertChannel,
    build_telegram_alert_channel_from_settings,
)
from market_screener.core.score_factors import SCORE_MODEL_VERSION
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.email_alert_dispatch import (
    EmailAlertDispatchJob,
    EmailAlertDispatchResult,
)
from market_screener.jobs.idempotency import build_idempotency_key

logger = logging.getLogger("market_screener.jobs.telegram_alert_dispatch")


def run_telegram_alert_dispatch(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    channel: TelegramAlertChannel | None = None,
    now_utc: datetime | None = None,
) -> EmailAlertDispatchResult:
    """Run telegram alert dispatch with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    resolved_channel = channel or build_telegram_alert_channel_from_settings(resolved_settings)
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    window_anchor_hour = reference_now.strftime("%Y-%m-%dT%H")

    idempotency_key = build_idempotency_key(
        "telegram_alert_dispatch",
        {
            "window_anchor_hour": window_anchor_hour,
            "symbol_limit": resolved_settings.alert_dispatch_symbol_limit,
            "lookback_hours": resolved_settings.alert_dispatch_lookback_hours,
            "signal_allowlist": resolved_settings.alert_dispatch_signal_allowlist,
            "min_score": resolved_settings.alert_dispatch_min_score,
            "max_per_day": resolved_settings.alert_max_per_day,
            "cooldown_minutes": resolved_settings.alert_cooldown_minutes,
            "model_version": SCORE_MODEL_VERSION,
        },
    )

    if resolved_audit.has_completed_run("telegram_alert_dispatch", idempotency_key):
        return EmailAlertDispatchResult(
            requested_assets=0,
            evaluated_assets=0,
            candidate_alerts=0,
            queued_alerts=0,
            sent_alerts=0,
            failed_alerts=0,
            skipped_no_signal=0,
            skipped_signal_not_allowed=0,
            skipped_below_threshold=0,
            skipped_blocked_risk=0,
            skipped_cooldown=0,
            skipped_daily_limit=0,
            skipped_channel=0,
            lookback_hours=resolved_settings.alert_dispatch_lookback_hours,
            min_score=resolved_settings.alert_dispatch_min_score,
            allowed_signals=sorted(
                _parse_signal_allowlist(resolved_settings.alert_dispatch_signal_allowlist)
            ),
            statuses=[],
            sent_symbols=[],
            idempotent_skip=True,
        )

    job = EmailAlertDispatchJob(
        resolved_session_factory,
        channel=resolved_channel,
        dispatch_job_name="telegram_alert_dispatch",
        symbol_limit=resolved_settings.alert_dispatch_symbol_limit,
        lookback_hours=resolved_settings.alert_dispatch_lookback_hours,
        min_score=resolved_settings.alert_dispatch_min_score,
        allowed_signals=_parse_signal_allowlist(resolved_settings.alert_dispatch_signal_allowlist),
        model_version=SCORE_MODEL_VERSION,
        max_per_day=resolved_settings.alert_max_per_day,
        cooldown_minutes=resolved_settings.alert_cooldown_minutes,
    )
    with resolved_audit.track_job_run(
        "telegram_alert_dispatch",
        details={
            "window_anchor_hour": window_anchor_hour,
            "symbol_limit": resolved_settings.alert_dispatch_symbol_limit,
            "lookback_hours": resolved_settings.alert_dispatch_lookback_hours,
            "signal_allowlist": resolved_settings.alert_dispatch_signal_allowlist,
            "min_score": resolved_settings.alert_dispatch_min_score,
            "max_per_day": resolved_settings.alert_max_per_day,
            "cooldown_minutes": resolved_settings.alert_cooldown_minutes,
            "idempotency_key": idempotency_key,
            "idempotency_hit": False,
        },
        idempotency_key=idempotency_key,
    ) as run_handle:
        result = job.run(now_utc=reference_now)
        run_handle.add_details(
            {
                "evaluated_assets": result.evaluated_assets,
                "candidate_alerts": result.candidate_alerts,
                "sent_alerts_count": result.sent_alerts,
                "failed_alerts": result.failed_alerts,
                "sent_alerts": [
                    {
                        "symbol": status.symbol,
                        "as_of_ts": status.as_of_ts.isoformat() if status.as_of_ts else None,
                        "sent_at": reference_now.isoformat(),
                    }
                    for status in result.statuses
                    if status.decision == "sent"
                ],
                "idempotent_skip": False,
            }
        )
        return result


def _parse_signal_allowlist(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def main() -> None:
    """CLI entrypoint for telegram alert dispatch."""

    result = run_telegram_alert_dispatch()
    logger.info(
        "telegram_alert_dispatch_completed",
        extra={
            "evaluated_assets": result.evaluated_assets,
            "candidate_alerts": result.candidate_alerts,
            "queued_alerts": result.queued_alerts,
            "sent_alerts": result.sent_alerts,
            "failed_alerts": result.failed_alerts,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "telegram_alert_dispatch:"
        f" evaluated_assets={result.evaluated_assets}"
        f" candidate_alerts={result.candidate_alerts}"
        f" queued_alerts={result.queued_alerts}"
        f" sent_alerts={result.sent_alerts}"
        f" failed_alerts={result.failed_alerts}"
        f" skipped_channel={result.skipped_channel}"
        f" idempotent_skip={result.idempotent_skip}"
    )


if __name__ == "__main__":
    main()
