"""Tests for SMTP email alert channel integration."""

from __future__ import annotations

from datetime import UTC, datetime

from market_screener.alerts.email_channel import EmailAlert, SmtpEmailAlertChannel


def test_email_channel_skips_when_disabled() -> None:
    channel = SmtpEmailAlertChannel(
        enabled=False,
        host="smtp.example.com",
        port=587,
        username="user",
        password="pw",
        sender="alerts@example.com",
        recipients=["owner@example.com"],
    )
    result = channel.send_alerts(
        [
            EmailAlert(
                symbol="AAPL",
                signal="strong_buy",
                score=82.5,
                confidence=0.82,
                as_of_ts=datetime(2026, 4, 23, 10, 0, tzinfo=UTC),
                reasons=["score_band_high"],
            )
        ]
    )

    assert result.sent_alerts == 0
    assert result.failed_alerts == 0
    assert result.skipped_reason == "channel_disabled"


def test_email_channel_skips_when_unconfigured() -> None:
    channel = SmtpEmailAlertChannel(
        enabled=True,
        host="",
        port=587,
        username=None,
        password=None,
        sender=None,
        recipients=[],
    )
    result = channel.send_alerts(
        [
            EmailAlert(
                symbol="AAPL",
                signal="strong_buy",
                score=82.5,
                confidence=0.82,
                as_of_ts=datetime(2026, 4, 23, 10, 0, tzinfo=UTC),
                reasons=["score_band_high"],
            )
        ]
    )

    assert result.sent_alerts == 0
    assert result.failed_alerts == 0
    assert result.skipped_reason == "channel_unconfigured"


def test_email_channel_sends_digest_using_smtp() -> None:
    captured: dict[str, object] = {}

    class _FakeSmtp:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            captured["host"] = host
            captured["port"] = port
            captured["timeout"] = timeout
            captured["starttls"] = 0
            captured["login"] = None
            captured["subject"] = None
            captured["body"] = None

        def __enter__(self) -> "_FakeSmtp":
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def ehlo(self):
            return (250, b"ok")

        def starttls(self):
            captured["starttls"] = int(captured["starttls"]) + 1
            return (220, b"tls")

        def login(self, user: str, password: str):
            captured["login"] = (user, password)
            return (235, b"ok")

        def send_message(self, message):
            captured["subject"] = message["Subject"]
            captured["body"] = message.get_content()
            captured["to"] = message["To"]
            return {}

    channel = SmtpEmailAlertChannel(
        enabled=True,
        host="smtp.example.com",
        port=587,
        username="smtp-user",
        password="smtp-password",
        sender="alerts@example.com",
        recipients=["owner@example.com"],
        smtp_factory=_FakeSmtp,
    )

    result = channel.send_alerts(
        [
            EmailAlert(
                symbol="AAPL",
                signal="strong_buy",
                score=84.2,
                confidence=0.78,
                as_of_ts=datetime(2026, 4, 23, 9, 0, tzinfo=UTC),
                reasons=["score_band_high", "bullish_trend"],
            ),
            EmailAlert(
                symbol="MSFT",
                signal="buy",
                score=74.1,
                confidence=0.67,
                as_of_ts=datetime(2026, 4, 23, 9, 0, tzinfo=UTC),
                reasons=["momentum_improving"],
            ),
        ],
        now_utc=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )

    assert result.sent_alerts == 2
    assert result.failed_alerts == 0
    assert result.skipped_reason is None
    assert captured["host"] == "smtp.example.com"
    assert captured["port"] == 587
    assert captured["starttls"] == 1
    assert captured["login"] == ("smtp-user", "smtp-password")
    assert "Market Screener Alerts (2)" in str(captured["subject"])
    assert "AAPL" in str(captured["body"])
    assert "MSFT" in str(captured["body"])
