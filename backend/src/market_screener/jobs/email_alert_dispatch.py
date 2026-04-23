"""Email alert dispatch job based on latest actionable signals."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from market_screener.alerts.email_channel import (
    EmailAlert,
    SmtpEmailAlertChannel,
    build_email_alert_channel_from_settings,
)
from market_screener.core.score_factors import SCORE_MODEL_VERSION
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, Job, SignalHistory
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.idempotency import build_idempotency_key

logger = logging.getLogger("market_screener.jobs.email_alert_dispatch")


@dataclass(frozen=True)
class EmailAlertAssetStatus:
    """Per-asset decision outcome for alert dispatch evaluation."""

    symbol: str
    signal: str | None
    score: float | None
    as_of_ts: datetime | None
    decision: str


@dataclass(frozen=True)
class EmailAlertDispatchResult:
    """Summary of one email alert dispatch run."""

    requested_assets: int
    evaluated_assets: int
    candidate_alerts: int
    queued_alerts: int
    sent_alerts: int
    failed_alerts: int
    skipped_no_signal: int
    skipped_signal_not_allowed: int
    skipped_below_threshold: int
    skipped_blocked_risk: int
    skipped_cooldown: int
    skipped_daily_limit: int
    skipped_channel: int
    lookback_hours: int
    min_score: float
    allowed_signals: list[str]
    statuses: list[EmailAlertAssetStatus]
    sent_symbols: list[str]
    idempotent_skip: bool = False


class EmailAlertDispatchJob:
    """Evaluate recent signals and dispatch actionable alerts via email."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        channel: SmtpEmailAlertChannel,
        symbol_limit: int,
        lookback_hours: int,
        min_score: float,
        allowed_signals: set[str],
        model_version: str,
        max_per_day: int,
        cooldown_minutes: int,
        recent_send_context_loader: (
            Callable[[object, datetime, int], tuple[int, set[str]]] | None
        ) = None,
    ) -> None:
        self._session_factory = session_factory
        self._channel = channel
        self._symbol_limit = max(1, symbol_limit)
        self._lookback_hours = max(1, lookback_hours)
        self._min_score = float(min_score)
        self._allowed_signals = {
            signal.strip().lower() for signal in allowed_signals if signal.strip()
        }
        if not self._allowed_signals:
            self._allowed_signals = {"strong_buy", "buy"}
        self._model_version = (model_version or "").strip() or SCORE_MODEL_VERSION
        self._max_per_day = max(1, max_per_day)
        self._cooldown_minutes = max(1, cooldown_minutes)
        self._recent_send_context_loader = recent_send_context_loader or _load_recent_send_context

    def run(self, *, now_utc: datetime | None = None) -> EmailAlertDispatchResult:
        """Run alert selection and send one digest email for eligible alerts."""

        reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
        lookback_cutoff = reference_now - timedelta(hours=self._lookback_hours)
        statuses: list[EmailAlertAssetStatus] = []
        candidates: list[EmailAlert] = []

        with self._session_factory() as session:
            assets = list(
                session.scalars(
                    select(Asset)
                    .where(Asset.active.is_(True))
                    .order_by(Asset.symbol.asc())
                    .limit(self._symbol_limit)
                ).all()
            )
            asset_ids = [asset.id for asset in assets]
            symbol_by_id = {asset.id: asset.symbol for asset in assets}

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

            latest_by_asset_id: dict[
                int, tuple[str, Decimal | None, Decimal | None, bool, list[str] | None, datetime]
            ] = {}
            for asset_id, signal, score, confidence, blocked_by_risk, reasons, as_of_ts in rows:
                if asset_id not in latest_by_asset_id:
                    latest_by_asset_id[asset_id] = (
                        signal,
                        score,
                        confidence,
                        bool(blocked_by_risk),
                        reasons,
                        normalize_to_utc(as_of_ts),
                    )

            sent_today_count, cooldown_symbols = self._recent_send_context_loader(
                session,
                reference_now,
                self._cooldown_minutes,
            )

            skipped_no_signal = 0
            skipped_signal_not_allowed = 0
            skipped_below_threshold = 0
            skipped_blocked_risk = 0
            skipped_cooldown = 0
            skipped_daily_limit = 0
            sent_symbols: list[str] = []

            for asset in assets:
                latest = latest_by_asset_id.get(asset.id)
                if latest is None:
                    skipped_no_signal += 1
                    statuses.append(
                        EmailAlertAssetStatus(
                            symbol=asset.symbol,
                            signal=None,
                            score=None,
                            as_of_ts=None,
                            decision="skipped_no_signal",
                        )
                    )
                    continue

                signal, score_decimal, confidence_decimal, blocked_by_risk, reasons, as_of_ts = (
                    latest
                )
                score = _to_float(score_decimal)
                confidence = _to_float(confidence_decimal)

                if signal.lower() not in self._allowed_signals:
                    skipped_signal_not_allowed += 1
                    statuses.append(
                        EmailAlertAssetStatus(
                            symbol=asset.symbol,
                            signal=signal,
                            score=score,
                            as_of_ts=as_of_ts,
                            decision="skipped_signal_not_allowed",
                        )
                    )
                    continue
                if blocked_by_risk:
                    skipped_blocked_risk += 1
                    statuses.append(
                        EmailAlertAssetStatus(
                            symbol=asset.symbol,
                            signal=signal,
                            score=score,
                            as_of_ts=as_of_ts,
                            decision="skipped_blocked_risk",
                        )
                    )
                    continue
                if score is None or score < self._min_score:
                    skipped_below_threshold += 1
                    statuses.append(
                        EmailAlertAssetStatus(
                            symbol=asset.symbol,
                            signal=signal,
                            score=score,
                            as_of_ts=as_of_ts,
                            decision="skipped_below_threshold",
                        )
                    )
                    continue

                if asset.symbol in cooldown_symbols:
                    skipped_cooldown += 1
                    statuses.append(
                        EmailAlertAssetStatus(
                            symbol=asset.symbol,
                            signal=signal,
                            score=score,
                            as_of_ts=as_of_ts,
                            decision="skipped_cooldown",
                        )
                    )
                    continue

                projected_total = sent_today_count + len(candidates) + 1
                if projected_total > self._max_per_day:
                    skipped_daily_limit += 1
                    statuses.append(
                        EmailAlertAssetStatus(
                            symbol=asset.symbol,
                            signal=signal,
                            score=score,
                            as_of_ts=as_of_ts,
                            decision="skipped_daily_limit",
                        )
                    )
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
        failed_alerts = delivery.failed_alerts
        skipped_channel = 0
        if delivery.skipped_reason is None and delivery.failed_alerts == 0:
            for candidate in candidates:
                sent_symbols.append(candidate.symbol)
                statuses.append(
                    EmailAlertAssetStatus(
                        symbol=candidate.symbol,
                        signal=candidate.signal,
                        score=candidate.score,
                        as_of_ts=candidate.as_of_ts,
                        decision="sent",
                    )
                )
        elif delivery.skipped_reason is not None:
            skipped_channel = len(candidates)
            for candidate in candidates:
                statuses.append(
                    EmailAlertAssetStatus(
                        symbol=candidate.symbol,
                        signal=candidate.signal,
                        score=candidate.score,
                        as_of_ts=candidate.as_of_ts,
                        decision=delivery.skipped_reason,
                    )
                )
        else:
            for candidate in candidates:
                statuses.append(
                    EmailAlertAssetStatus(
                        symbol=candidate.symbol,
                        signal=candidate.signal,
                        score=candidate.score,
                        as_of_ts=candidate.as_of_ts,
                        decision="failed_delivery",
                    )
                )

        return EmailAlertDispatchResult(
            requested_assets=self._symbol_limit,
            evaluated_assets=len(symbol_by_id),
            candidate_alerts=len(candidates),
            queued_alerts=len(candidates),
            sent_alerts=delivery.sent_alerts,
            failed_alerts=failed_alerts,
            skipped_no_signal=skipped_no_signal,
            skipped_signal_not_allowed=skipped_signal_not_allowed,
            skipped_below_threshold=skipped_below_threshold,
            skipped_blocked_risk=skipped_blocked_risk,
            skipped_cooldown=skipped_cooldown,
            skipped_daily_limit=skipped_daily_limit,
            skipped_channel=skipped_channel,
            lookback_hours=self._lookback_hours,
            min_score=self._min_score,
            allowed_signals=sorted(self._allowed_signals),
            statuses=statuses,
            sent_symbols=sorted(sent_symbols),
        )


def run_email_alert_dispatch(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    channel: SmtpEmailAlertChannel | None = None,
    now_utc: datetime | None = None,
) -> EmailAlertDispatchResult:
    """Run email alert dispatch with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    resolved_channel = channel or build_email_alert_channel_from_settings(resolved_settings)
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    window_anchor_hour = reference_now.strftime("%Y-%m-%dT%H")

    idempotency_key = build_idempotency_key(
        "email_alert_dispatch",
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

    if resolved_audit.has_completed_run("email_alert_dispatch", idempotency_key):
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
        symbol_limit=resolved_settings.alert_dispatch_symbol_limit,
        lookback_hours=resolved_settings.alert_dispatch_lookback_hours,
        min_score=resolved_settings.alert_dispatch_min_score,
        allowed_signals=_parse_signal_allowlist(resolved_settings.alert_dispatch_signal_allowlist),
        model_version=SCORE_MODEL_VERSION,
        max_per_day=resolved_settings.alert_max_per_day,
        cooldown_minutes=resolved_settings.alert_cooldown_minutes,
    )
    with resolved_audit.track_job_run(
        "email_alert_dispatch",
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


def _load_recent_send_context(
    session,
    now_utc: datetime,
    cooldown_minutes: int,
) -> tuple[int, set[str]]:
    day_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=UTC)
    cooldown_cutoff = now_utc - timedelta(minutes=cooldown_minutes)
    try:
        rows = list(
            session.scalars(
                select(Job)
                .where(
                    Job.job_name == "email_alert_dispatch",
                    Job.status == "completed",
                    Job.started_at >= day_start,
                    Job.started_at <= now_utc,
                )
                .order_by(Job.started_at.desc())
            ).all()
        )
    except Exception:
        return 0, set()

    sent_events: list[tuple[str, datetime]] = []
    for job_row in rows:
        details = job_row.details if isinstance(job_row.details, dict) else {}
        sent_alerts = details.get("sent_alerts")
        if not isinstance(sent_alerts, list):
            continue
        for item in sent_alerts:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if not isinstance(symbol, str) or not symbol.strip():
                continue
            sent_at = _parse_event_timestamp(item.get("sent_at"), fallback=job_row.started_at)
            sent_events.append((symbol.strip(), sent_at))

    cooldown_symbols = {
        symbol for symbol, sent_at in sent_events if normalize_to_utc(sent_at) >= cooldown_cutoff
    }
    return len(sent_events), cooldown_symbols


def _parse_event_timestamp(value: object, *, fallback: datetime) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            return normalize_to_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return normalize_to_utc(fallback)
    return normalize_to_utc(fallback)


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def main() -> None:
    """CLI entrypoint for email alert dispatch."""

    result = run_email_alert_dispatch()
    logger.info(
        "email_alert_dispatch_completed",
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
        "email_alert_dispatch:"
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
