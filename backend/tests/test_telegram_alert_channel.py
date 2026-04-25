"""Tests for Telegram alert channel integration."""

from __future__ import annotations

from datetime import UTC, datetime

from market_screener.alerts.email_channel import EmailAlert
from market_screener.alerts.telegram_channel import TelegramAlertChannel


def test_telegram_channel_skips_when_disabled() -> None:
    channel = TelegramAlertChannel(
        enabled=False,
        bot_token="token",
        chat_id="chat",
    )
    result = channel.send_alerts(
        [
            EmailAlert(
                symbol="AAPL",
                signal="strong_buy",
                score=82.0,
                confidence=0.8,
                as_of_ts=datetime(2026, 4, 23, 10, 0, tzinfo=UTC),
                reasons=[],
            )
        ]
    )

    assert result.sent_alerts == 0
    assert result.failed_alerts == 0
    assert result.skipped_reason == "channel_disabled"


def test_telegram_channel_skips_when_unconfigured() -> None:
    channel = TelegramAlertChannel(
        enabled=True,
        bot_token="",
        chat_id="",
    )
    result = channel.send_alerts(
        [
            EmailAlert(
                symbol="AAPL",
                signal="strong_buy",
                score=82.0,
                confidence=0.8,
                as_of_ts=datetime(2026, 4, 23, 10, 0, tzinfo=UTC),
                reasons=[],
            )
        ]
    )

    assert result.sent_alerts == 0
    assert result.failed_alerts == 0
    assert result.skipped_reason == "channel_unconfigured"


def test_telegram_channel_posts_digest_message() -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

    class _FakeClient:
        def post(self, url: str, *, json: dict[str, object], timeout: int):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return _FakeResponse()

    channel = TelegramAlertChannel(
        enabled=True,
        bot_token="bot-token",
        chat_id="chat-id",
        http_client=_FakeClient(),
    )
    result = channel.send_alerts(
        [
            EmailAlert(
                symbol="AAPL",
                signal="strong_buy",
                score=84.2,
                confidence=0.81,
                as_of_ts=datetime(2026, 4, 23, 9, 0, tzinfo=UTC),
                reasons=["score_band_high"],
            ),
            EmailAlert(
                symbol="MSFT",
                signal="buy",
                score=74.3,
                confidence=0.69,
                as_of_ts=datetime(2026, 4, 23, 9, 0, tzinfo=UTC),
                reasons=["momentum_improving"],
            ),
        ],
        now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )

    assert result.sent_alerts == 2
    assert result.failed_alerts == 0
    assert "https://api.telegram.org/botbot-token/sendMessage" == captured["url"]
    assert "AAPL" in str(captured["json"])
    assert "MSFT" in str(captured["json"])
