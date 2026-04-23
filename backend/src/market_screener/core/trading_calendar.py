"""Trading-calendar helpers for market-closure handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from market_screener.core.settings import Settings


@dataclass(frozen=True)
class TradingCalendar:
    """Weekend + manual-holiday calendar per market segment."""

    us_holidays: set[date] = field(default_factory=set)
    nse_holidays: set[date] = field(default_factory=set)
    global_holidays: set[date] = field(default_factory=set)

    @classmethod
    def from_settings(cls, settings: Settings) -> "TradingCalendar":
        """Build calendar from runtime holiday configuration."""

        return cls(
            us_holidays=parse_holiday_csv(settings.market_holidays_us),
            nse_holidays=parse_holiday_csv(settings.market_holidays_nse),
            global_holidays=parse_holiday_csv(settings.market_holidays_global),
        )

    def is_market_open(
        self,
        *,
        asset_type: str,
        exchange: str | None,
        on_date: date | datetime,
    ) -> bool:
        """Return whether the market is expected open for this asset/date."""

        target_date = normalize_to_date(on_date)
        normalized_asset = asset_type.lower()
        normalized_exchange = (exchange or "").upper()

        if normalized_asset == "crypto":
            return True

        if target_date.weekday() >= 5:
            return False

        holidays = self._holidays_for_market(
            asset_type=normalized_asset,
            exchange=normalized_exchange,
        )
        if target_date in holidays:
            return False

        return True

    def closure_reason(
        self,
        *,
        asset_type: str,
        exchange: str | None,
        on_date: date | datetime,
    ) -> str | None:
        """Return closure reason when closed, else None."""

        target_date = normalize_to_date(on_date)
        normalized_asset = asset_type.lower()
        normalized_exchange = (exchange or "").upper()

        if normalized_asset == "crypto":
            return None
        if target_date.weekday() >= 5:
            return "weekend"

        holidays = self._holidays_for_market(
            asset_type=normalized_asset,
            exchange=normalized_exchange,
        )
        if target_date in holidays:
            return "holiday"
        return None

    def _holidays_for_market(self, *, asset_type: str, exchange: str) -> set[date]:
        if asset_type == "equity":
            if exchange in {"US", "NYSE", "NASDAQ"}:
                return self.us_holidays
            if exchange in {"NSE", "BSE"}:
                return self.nse_holidays
            return self.global_holidays

        if asset_type in {"forex", "commodity", "index"}:
            return self.global_holidays

        return set()


def parse_holiday_csv(raw: str) -> set[date]:
    """Parse comma-separated YYYY-MM-DD holiday list."""

    holidays: set[date] = set()
    for token in raw.split(","):
        text = token.strip()
        if not text:
            continue
        try:
            holidays.add(datetime.strptime(text, "%Y-%m-%d").date())
        except ValueError as exc:
            raise ValueError(f"holiday_date_must_match_yyyy_mm_dd: {text}") from exc
    return holidays


def normalize_to_date(value: date | datetime) -> date:
    """Normalize datetime/date inputs to UTC calendar date."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.date()
    return value
