"""Telegram alert channel integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from market_screener.alerts.email_channel import EmailAlert, EmailAlertDeliveryResult
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc


class _HttpClient(Protocol):
    def post(self, url: str, *, json: dict[str, object], timeout: int) -> object: ...


@dataclass(frozen=True)
class TelegramAlertChannel:
    """Telegram bot channel for alert digest delivery."""

    enabled: bool
    bot_token: str | None
    chat_id: str | None
    timeout_seconds: int = 15
    api_base_url: str = "https://api.telegram.org"
    http_client: _HttpClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool((self.bot_token or "").strip() and (self.chat_id or "").strip())

    def send_alerts(
        self,
        alerts: list[EmailAlert],
        *,
        now_utc: datetime | None = None,
    ) -> EmailAlertDeliveryResult:
        attempted = len(alerts)
        if attempted == 0:
            return EmailAlertDeliveryResult(attempted_alerts=0, sent_alerts=0, failed_alerts=0)
        if not self.enabled:
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

        token = (self.bot_token or "").strip()
        chat_id = (self.chat_id or "").strip()
        text = _render_telegram_message(alerts, now_utc=now_utc)
        endpoint = f"{self.api_base_url.rstrip('/')}/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        client = self.http_client or httpx
        try:
            response = client.post(endpoint, json=payload, timeout=max(1, self.timeout_seconds))
            status_code = int(getattr(response, "status_code", 500))
            if status_code >= 400:
                return EmailAlertDeliveryResult(
                    attempted_alerts=attempted,
                    sent_alerts=0,
                    failed_alerts=attempted,
                    error_message=f"telegram_http_{status_code}",
                )
        except Exception as exc:  # pragma: no cover - covered via fake client tests.
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


def build_telegram_alert_channel_from_settings(
    settings: Settings | None = None,
    *,
    http_client: _HttpClient | None = None,
) -> TelegramAlertChannel:
    """Create Telegram channel from runtime settings."""

    resolved = settings or get_settings()
    return TelegramAlertChannel(
        enabled=resolved.alert_channel_telegram_enabled,
        bot_token=resolved.telegram_bot_token,
        chat_id=resolved.telegram_chat_id,
        http_client=http_client,
    )


def _render_telegram_message(
    alerts: list[EmailAlert],
    *,
    now_utc: datetime | None,
) -> str:
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    lines = [
        f"Market Screener Alerts ({len(alerts)})",
        f"Generated: {reference_now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    for alert in alerts:
        score_text = "-" if alert.score is None else f"{alert.score:.2f}"
        confidence_text = "-" if alert.confidence is None else f"{alert.confidence:.2f}"
        lines.append(
            f"{alert.symbol} | {alert.signal} | score {score_text} | conf {confidence_text}"
        )
    return "\n".join(lines).strip()
