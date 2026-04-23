"""Tests for trading calendar closure handling."""

from __future__ import annotations

from datetime import date

from market_screener.core.settings import Settings
from market_screener.core.trading_calendar import TradingCalendar, parse_holiday_csv


def test_parse_holiday_csv_supports_empty_and_multiple_dates() -> None:
    parsed = parse_holiday_csv("2026-01-01, 2026-12-25")
    assert parsed == {date(2026, 1, 1), date(2026, 12, 25)}
    assert parse_holiday_csv("") == set()


def test_trading_calendar_applies_weekend_rules() -> None:
    calendar = TradingCalendar()

    saturday = date(2026, 4, 25)
    assert calendar.is_market_open(asset_type="crypto", exchange="GLOBAL", on_date=saturday) is True
    assert calendar.is_market_open(asset_type="equity", exchange="US", on_date=saturday) is False
    assert calendar.is_market_open(asset_type="forex", exchange="GLOBAL", on_date=saturday) is False
    assert (
        calendar.closure_reason(asset_type="equity", exchange="US", on_date=saturday) == "weekend"
    )


def test_trading_calendar_applies_exchange_holidays() -> None:
    settings = Settings(
        market_holidays_us="2026-07-03",
        market_holidays_nse="2026-08-15",
        market_holidays_global="2026-01-01",
    )
    calendar = TradingCalendar.from_settings(settings)

    assert (
        calendar.is_market_open(asset_type="equity", exchange="US", on_date=date(2026, 7, 3))
        is False
    )
    assert (
        calendar.is_market_open(asset_type="equity", exchange="NSE", on_date=date(2026, 8, 15))
        is False
    )
    assert (
        calendar.is_market_open(asset_type="commodity", exchange="GLOBAL", on_date=date(2026, 1, 1))
        is False
    )
    assert (
        calendar.is_market_open(asset_type="equity", exchange="US", on_date=date(2026, 7, 6))
        is True
    )
