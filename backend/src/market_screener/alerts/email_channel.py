"""SMTP email alert channel integration."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol

from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc


@dataclass(frozen=True)
class EmailAlert:
    """One alert payload rendered into an email digest."""

    symbol: str
    signal: str
    score: float | None
    confidence: float | None
    as_of_ts: datetime
    reasons: list[str]


@dataclass(frozen=True)
class EmailAlertDeliveryResult:
    """Delivery summary for a single email-alert send attempt."""

    attempted_alerts: int
    sent_alerts: int
    failed_alerts: int
    skipped_reason: str | None = None
    error_message: str | None = None


class _SmtpClient(Protocol):
    def __enter__(self): ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

    def ehlo(self) -> tuple[int, bytes]: ...

    def starttls(self) -> tuple[int, bytes]: ...

    def login(self, user: str, password: str) -> tuple[int, bytes]: ...

    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]: ...


class SmtpEmailAlertChannel:
    """SMTP email channel that sends one digest for an alert batch."""

    def __init__(
        self,
        *,
        enabled: bool,
        host: str | None,
        port: int,
        username: str | None,
        password: str | None,
        sender: str | None,
        recipients: list[str],
        use_starttls: bool = True,
        timeout_seconds: int = 15,
        smtp_factory=smtplib.SMTP,
    ) -> None:
        self._enabled = enabled
        self._host = (host or "").strip()
        self._port = max(1, int(port))
        self._username = (username or "").strip() or None
        self._password = (password or "").strip() or None
        self._sender = (sender or "").strip() or None
        self._recipients = [value.strip() for value in recipients if value.strip()]
        self._use_starttls = use_starttls
        self._timeout_seconds = max(1, timeout_seconds)
        self._smtp_factory = smtp_factory

    @property
    def is_enabled(self) -> bool:
        """Whether email alerts are enabled in runtime settings."""

        return self._enabled

    @property
    def is_configured(self) -> bool:
        """Whether SMTP host/from/to are configured enough to send."""

        return bool(self._host and self._sender and self._recipients)

    def send_alerts(
        self,
        alerts: list[EmailAlert],
        *,
        now_utc: datetime | None = None,
    ) -> EmailAlertDeliveryResult:
        """Send one digest email for alert payloads."""

        attempted = len(alerts)
        if attempted == 0:
            return EmailAlertDeliveryResult(attempted_alerts=0, sent_alerts=0, failed_alerts=0)
        if not self._enabled:
            return EmailAlertDeliveryResult(
                attempted_alerts=attempted,
                sent_alerts=0,
                failed_alerts=0,
                skipped_reason="channel_disabled",
            )
        if not self.is_configured:
            return EmailAlertDeliveryResult(
                attempted_alerts=attempted,
                sent_alerts=0,
                failed_alerts=0,
                skipped_reason="channel_unconfigured",
            )

        message = self._build_digest_message(alerts, now_utc=now_utc)
        try:
            with self._smtp_factory(
                self._host,
                self._port,
                timeout=self._timeout_seconds,
            ) as client:
                smtp_client: _SmtpClient = client
                smtp_client.ehlo()
                if self._use_starttls:
                    smtp_client.starttls()
                    smtp_client.ehlo()
                if self._username and self._password:
                    smtp_client.login(self._username, self._password)
                smtp_client.send_message(message)
        except Exception as exc:  # pragma: no cover - covered via tests with fake SMTP raising.
            return EmailAlertDeliveryResult(
                attempted_alerts=attempted,
                sent_alerts=0,
                failed_alerts=attempted,
                error_message=str(exc)[:500],
            )

        return EmailAlertDeliveryResult(
            attempted_alerts=attempted,
            sent_alerts=attempted,
            failed_alerts=0,
        )

    def _build_digest_message(
        self,
        alerts: list[EmailAlert],
        *,
        now_utc: datetime | None,
    ) -> EmailMessage:
        reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = ", ".join(self._recipients)
        message["Subject"] = (
            f"Market Screener Alerts ({len(alerts)}) - {reference_now.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        message.set_content(_render_email_digest(alerts, reference_now=reference_now))
        return message


def build_email_alert_channel_from_settings(
    settings: Settings | None = None,
    *,
    smtp_factory=smtplib.SMTP,
) -> SmtpEmailAlertChannel:
    """Create email alert channel from runtime settings."""

    resolved = settings or get_settings()
    recipients = _parse_recipients(resolved.smtp_to)
    return SmtpEmailAlertChannel(
        enabled=resolved.alert_channel_email_enabled,
        host=resolved.smtp_host,
        port=resolved.smtp_port,
        username=resolved.smtp_username,
        password=resolved.smtp_password,
        sender=resolved.smtp_from,
        recipients=recipients,
        smtp_factory=smtp_factory,
    )


def _render_email_digest(alerts: list[EmailAlert], *, reference_now: datetime) -> str:
    lines = [
        "Market Screener alert digest",
        f"Generated at: {reference_now.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]
    for index, alert in enumerate(alerts, start=1):
        score_text = "-" if alert.score is None else f"{alert.score:.2f}"
        confidence_text = "-" if alert.confidence is None else f"{alert.confidence:.2f}"
        as_of_text = normalize_to_utc(alert.as_of_ts).strftime("%Y-%m-%d %H:%M:%S UTC")
        reasons_text = ", ".join(alert.reasons) if alert.reasons else "n/a"
        lines.extend(
            [
                f"{index}. {alert.symbol}",
                f"   signal: {alert.signal}",
                f"   score: {score_text}",
                f"   confidence: {confidence_text}",
                f"   as_of: {as_of_text}",
                f"   reasons: {reasons_text}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _parse_recipients(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
