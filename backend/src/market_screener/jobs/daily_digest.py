"""Daily digest job for paper-trading style validation and non-spammy summaries."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select

from market_screener.alerts.email_channel import (
    EmailAlert,
    EmailAlertDeliveryResult,
    SmtpEmailAlertChannel,
)
from market_screener.alerts.telegram_channel import TelegramAlertChannel
from market_screener.core.score_factors import SCORE_MODEL_VERSION
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, SignalHistory
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.idempotency import build_idempotency_key

logger = logging.getLogger("market_screener.jobs.daily_digest")


class DigestChannel(Protocol):
    def send_alerts(
        self, alerts: list[EmailAlert], *, now_utc: datetime | None = None
    ) -> EmailAlertDeliveryResult: ...


@dataclass(frozen=True)
class DailyDigestResult:
    requested_assets: int
    evaluated_assets: int
    candidates: int
    sent: int
    failed: int
    skipped_channel: int
    lookback_hours: int
    min_score: float
    allowed_signals: list[str]
    idempotent_skip: bool = False


class DailyDigestJob:
    """Select top daily candidates and send one digest via one channel."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        channel: DigestChannel,
        dispatch_job_name: str,
        symbol_limit: int,
        lookback_hours: int,
        min_score: float,
        allowed_signals: set[str],
        model_version: str,
        include_blocked_by_risk: bool,
    ) -> None:
        self._session_factory = session_factory
        self._channel = channel
        self._dispatch_job_name = (dispatch_job_name or "").strip() or "daily_digest"
        self._symbol_limit = max(1, int(symbol_limit))
        self._lookback_hours = max(1, int(lookback_hours))
        self._min_score = float(min_score)
        self._allowed_signals = {s.strip().lower() for s in allowed_signals if s.strip()}
        if not self._allowed_signals:
            self._allowed_signals = {"strong_buy", "buy"}
        self._model_version = (model_version or "").strip() or SCORE_MODEL_VERSION
        self._include_blocked_by_risk = bool(include_blocked_by_risk)

    def run(self, *, now_utc: datetime | None = None) -> DailyDigestResult:
        reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
        lookback_cutoff = reference_now - timedelta(hours=self._lookback_hours)

        candidates: list[EmailAlert] = []
        evaluated_assets = 0

        with self._session_factory() as session:
            assets = list(
                session.scalars(
                    select(Asset)
                    .where(Asset.active.is_(True))
                    .order_by(Asset.symbol.asc())
                    .limit(self._symbol_limit)
                ).all()
            )
            evaluated_assets = len(assets)
            asset_ids = [asset.id for asset in assets]

            rows = list(
                session.execute(
                    select(
                        SignalHistory.asset_id,
                        SignalHistory.signal,
                        SignalHistory.score,
                        SignalHistory.confidence,
                        SignalHistory.blocked_by_risk,
                        SignalHistory.reasons,
                        SignalHistory.as_of_ts,
                    )
                    .where(
                        SignalHistory.asset_id.in_(asset_ids),
                        SignalHistory.model_version == self._model_version,
                        SignalHistory.as_of_ts >= lookback_cutoff,
                        SignalHistory.as_of_ts <= reference_now,
                    )
                    .order_by(SignalHistory.asset_id.asc(), SignalHistory.as_of_ts.desc())
                ).all()
            )

            latest_by_asset_id: dict[int, tuple] = {}
            for row in rows:
                asset_id = int(row[0])
                if asset_id in latest_by_asset_id:
                    continue
                latest_by_asset_id[asset_id] = row

            asset_by_id = {asset.id: asset for asset in assets}

            for asset_id, row in latest_by_asset_id.items():
                asset = asset_by_id.get(asset_id)
                if asset is None:
                    continue
                signal = str(row[1] or "").strip()
                if not signal:
                    continue
                score = _to_float(row[2])
                confidence = _to_float(row[3])
                blocked_by_risk = bool(row[4] or False)
                reasons = row[5] if isinstance(row[5], list) else []
                as_of_ts = normalize_to_utc(row[6])

                if signal.lower() not in self._allowed_signals:
                    continue
                if (score is None) or score < self._min_score:
                    continue
                if (not self._include_blocked_by_risk) and blocked_by_risk:
                    continue

                candidates.append(
                    EmailAlert(
                        symbol=asset.symbol,
                        signal=signal,
                        score=score,
                        confidence=confidence,
                        as_of_ts=as_of_ts,
                        reasons=reasons or [],
                    )
                )

        candidates.sort(
            key=lambda item: (
                -9999.0 if item.score is None else -item.score,
                normalize_to_utc(item.as_of_ts),
                item.symbol,
            )
        )

        delivery = self._channel.send_alerts(candidates, now_utc=reference_now)
        skipped_channel = 0
        if delivery.skipped_reason is not None:
            skipped_channel = len(candidates)

        return DailyDigestResult(
            requested_assets=self._symbol_limit,
            evaluated_assets=evaluated_assets,
            candidates=len(candidates),
            sent=delivery.sent_alerts,
            failed=delivery.failed_alerts,
            skipped_channel=skipped_channel,
            lookback_hours=self._lookback_hours,
            min_score=self._min_score,
            allowed_signals=sorted(self._allowed_signals),
        )


def run_daily_digest(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    """Run daily digest dispatch (telegram and email if enabled/configured)."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    day_anchor = reference_now.strftime("%Y-%m-%d")

    allowed_signals = _parse_signal_allowlist(
        resolved_settings.daily_digest_signal_allowlist
        or resolved_settings.alert_dispatch_signal_allowlist
    )
    min_score = float(
        resolved_settings.daily_digest_min_score
        if resolved_settings.daily_digest_min_score is not None
        else resolved_settings.alert_dispatch_min_score
    )
    lookback_hours = int(resolved_settings.daily_digest_lookback_hours)
    symbol_limit = int(resolved_settings.daily_digest_symbol_limit)
    include_blocked = bool(resolved_settings.daily_digest_include_blocked_by_risk)

    results: dict[str, object] = {"status": "ok", "day_anchor": day_anchor, "channels": {}}

    for channel_name, channel in _build_digest_channels(resolved_settings).items():
        idempotency_key = build_idempotency_key(
            f"{channel_name}_daily_digest",
            {
                "day_anchor": day_anchor,
                "symbol_limit": symbol_limit,
                "lookback_hours": lookback_hours,
                "allowed_signals": ",".join(sorted(allowed_signals)),
                "min_score": min_score,
                "include_blocked": include_blocked,
                "model_version": SCORE_MODEL_VERSION,
            },
        )
        job_name = f"{channel_name}_daily_digest"
        if resolved_audit.has_completed_run(job_name, idempotency_key):
            results["channels"][channel_name] = {"idempotent_skip": True}
            continue

        job = DailyDigestJob(
            resolved_session_factory,
            channel=channel,
            dispatch_job_name=job_name,
            symbol_limit=symbol_limit,
            lookback_hours=lookback_hours,
            min_score=min_score,
            allowed_signals=allowed_signals,
            model_version=SCORE_MODEL_VERSION,
            include_blocked_by_risk=include_blocked,
        )

        with resolved_audit.track_job_run(
            job_name,
            details={
                "day_anchor": day_anchor,
                "symbol_limit": symbol_limit,
                "lookback_hours": lookback_hours,
                "allowed_signals": sorted(allowed_signals),
                "min_score": min_score,
                "include_blocked": include_blocked,
                "idempotency_key": idempotency_key,
                "idempotency_hit": False,
            },
            idempotency_key=idempotency_key,
        ) as run_handle:
            result = job.run(now_utc=reference_now)
            run_handle.add_details(
                {
                    "evaluated_assets": result.evaluated_assets,
                    "candidates": result.candidates,
                    "sent": result.sent,
                    "failed": result.failed,
                    "skipped_channel": result.skipped_channel,
                }
            )
            results["channels"][channel_name] = {
                "requested_assets": result.requested_assets,
                "evaluated_assets": result.evaluated_assets,
                "candidates": result.candidates,
                "sent": result.sent,
                "failed": result.failed,
                "skipped_channel": result.skipped_channel,
                "idempotent_skip": False,
            }

    return results


def _build_digest_channels(settings: Settings) -> dict[str, DigestChannel]:
    channels: dict[str, DigestChannel] = {}
    channels["telegram"] = TelegramAlertChannel(
        enabled=settings.daily_digest_telegram_enabled and settings.alert_channel_telegram_enabled,
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    channels["email"] = SmtpEmailAlertChannel(
        enabled=settings.daily_digest_email_enabled and settings.alert_channel_email_enabled,
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        sender=settings.smtp_from,
        recipients=[item.strip() for item in (settings.smtp_to or "").split(",") if item.strip()],
    )
    return channels


def _parse_signal_allowlist(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def main() -> None:
    payload = run_daily_digest()
    logger.info("daily_digest_completed", extra={"channels": payload.get("channels")})
    print(payload)


if __name__ == "__main__":
    main()
