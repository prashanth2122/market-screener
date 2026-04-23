"""Watchlist price freshness monitoring workflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, Price
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail

logger = logging.getLogger("market_screener.jobs.freshness_monitor")


def parse_watchlist_symbols(raw_value: str) -> list[str]:
    """Parse comma-separated watchlist symbols into a normalized list."""

    parsed: list[str] = []
    seen: set[str] = set()
    for part in raw_value.split(","):
        symbol = part.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        parsed.append(symbol)
    return parsed


@dataclass(frozen=True)
class SymbolFreshnessStatus:
    """Per-symbol freshness status for the watchlist monitor."""

    symbol: str
    asset_type: str | None
    latest_ts: datetime | None
    age_minutes: int | None
    status: str
    failure_reason: str | None = None


@dataclass(frozen=True)
class WatchlistFreshnessResult:
    """Summary for one watchlist freshness monitoring run."""

    requested_symbols: int
    checked_symbols: int
    unknown_symbols: int
    fresh_symbols: int
    warning_symbols: int
    stale_symbols: int
    missing_symbols: int
    target_age_minutes: int
    max_age_minutes: int
    symbol_statuses: list[SymbolFreshnessStatus]

    @property
    def overall_success(self) -> bool:
        """True when all watched symbols are known and within freshness limits."""

        return (
            self.checked_symbols > 0
            and self.unknown_symbols == 0
            and self.missing_symbols == 0
            and self.stale_symbols == 0
        )


class WatchlistFreshnessMonitorJob:
    """Monitor latest price freshness for the configured watchlist."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        watchlist_symbols: list[str],
        target_age_minutes: int,
        max_age_minutes: int,
    ) -> None:
        self._session_factory = session_factory
        self._watchlist_symbols = [symbol.upper() for symbol in watchlist_symbols]
        self._target_age_minutes = max(1, target_age_minutes)
        self._max_age_minutes = max(self._target_age_minutes, max_age_minutes)

    def run(self, *, now_utc: datetime | None = None) -> WatchlistFreshnessResult:
        """Run freshness checks for watchlist symbols."""

        reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
        if not self._watchlist_symbols:
            return WatchlistFreshnessResult(
                requested_symbols=0,
                checked_symbols=0,
                unknown_symbols=0,
                fresh_symbols=0,
                warning_symbols=0,
                stale_symbols=0,
                missing_symbols=0,
                target_age_minutes=self._target_age_minutes,
                max_age_minutes=self._max_age_minutes,
                symbol_statuses=[],
            )

        with self._session_factory() as session:
            assets = session.execute(
                select(Asset.id, Asset.symbol, Asset.asset_type).where(
                    Asset.symbol.in_(self._watchlist_symbols),
                    Asset.active.is_(True),
                )
            ).all()

        asset_by_symbol = {
            symbol.upper(): (asset_id, asset_type) for asset_id, symbol, asset_type in assets
        }
        asset_ids = [asset_id for asset_id, _ in asset_by_symbol.values()]

        latest_ts_by_asset: dict[int, datetime] = {}
        if asset_ids:
            with self._session_factory() as session:
                rows = session.execute(
                    select(Price.asset_id, func.max(Price.ts))
                    .where(Price.asset_id.in_(asset_ids))
                    .group_by(Price.asset_id)
                ).all()
            latest_ts_by_asset = {
                asset_id: normalize_to_utc(ts) for asset_id, ts in rows if ts is not None
            }

        fresh_symbols = 0
        warning_symbols = 0
        stale_symbols = 0
        missing_symbols = 0
        unknown_symbols = 0
        statuses: list[SymbolFreshnessStatus] = []

        target_delta = timedelta(minutes=self._target_age_minutes)
        max_delta = timedelta(minutes=self._max_age_minutes)
        for symbol in self._watchlist_symbols:
            asset_entry = asset_by_symbol.get(symbol)
            if asset_entry is None:
                unknown_symbols += 1
                statuses.append(
                    SymbolFreshnessStatus(
                        symbol=symbol,
                        asset_type=None,
                        latest_ts=None,
                        age_minutes=None,
                        status="unknown",
                        failure_reason="symbol_not_found_or_inactive",
                    )
                )
                continue

            asset_id, asset_type = asset_entry
            latest_ts = latest_ts_by_asset.get(asset_id)
            if latest_ts is None:
                missing_symbols += 1
                statuses.append(
                    SymbolFreshnessStatus(
                        symbol=symbol,
                        asset_type=asset_type,
                        latest_ts=None,
                        age_minutes=None,
                        status="missing",
                        failure_reason="missing_price",
                    )
                )
                continue

            age_delta = reference_now - latest_ts
            age_minutes = max(0, int(age_delta.total_seconds() // 60))
            if age_delta <= target_delta:
                status = "fresh"
                failure_reason = None
                fresh_symbols += 1
            elif age_delta <= max_delta:
                status = "warning"
                failure_reason = "target_breached"
                warning_symbols += 1
            else:
                status = "stale"
                failure_reason = "max_age_breached"
                stale_symbols += 1

            statuses.append(
                SymbolFreshnessStatus(
                    symbol=symbol,
                    asset_type=asset_type,
                    latest_ts=latest_ts,
                    age_minutes=age_minutes,
                    status=status,
                    failure_reason=failure_reason,
                )
            )

        checked_symbols = len(self._watchlist_symbols) - unknown_symbols
        return WatchlistFreshnessResult(
            requested_symbols=len(self._watchlist_symbols),
            checked_symbols=checked_symbols,
            unknown_symbols=unknown_symbols,
            fresh_symbols=fresh_symbols,
            warning_symbols=warning_symbols,
            stale_symbols=stale_symbols,
            missing_symbols=missing_symbols,
            target_age_minutes=self._target_age_minutes,
            max_age_minutes=self._max_age_minutes,
            symbol_statuses=statuses,
        )


def run_watchlist_freshness_monitor(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> WatchlistFreshnessResult:
    """Run watchlist freshness monitoring with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    watchlist_symbols = parse_watchlist_symbols(resolved_settings.watchlist_symbols)

    if not watchlist_symbols:
        with resolved_session_factory() as session:
            watchlist_symbols = list(
                session.scalars(
                    select(Asset.symbol)
                    .where(Asset.active.is_(True))
                    .order_by(Asset.symbol.asc())
                    .limit(resolved_settings.freshness_monitor_symbol_limit)
                ).all()
            )

    job = WatchlistFreshnessMonitorJob(
        resolved_session_factory,
        watchlist_symbols=watchlist_symbols,
        target_age_minutes=resolved_settings.freshness_monitor_target_age_minutes,
        max_age_minutes=resolved_settings.max_stale_price_minutes,
    )
    with resolved_audit.track_job_run(
        "watchlist_freshness_monitor",
        details={
            "target_age_minutes": resolved_settings.freshness_monitor_target_age_minutes,
            "max_age_minutes": resolved_settings.max_stale_price_minutes,
            "watchlist_symbols": watchlist_symbols,
            "watchlist_source": (
                "settings"
                if resolved_settings.watchlist_symbols.strip()
                else "active_assets_fallback"
            ),
        },
    ) as run_handle:
        result = job.run(now_utc=now_utc)
        run_handle.add_details(
            {
                "requested_symbols": result.requested_symbols,
                "checked_symbols": result.checked_symbols,
                "unknown_symbols": result.unknown_symbols,
                "fresh_symbols": result.fresh_symbols,
                "warning_symbols": result.warning_symbols,
                "stale_symbols": result.stale_symbols,
                "missing_symbols": result.missing_symbols,
                "overall_success": result.overall_success,
            }
        )
        return result


def main() -> None:
    """CLI entrypoint for watchlist freshness monitor runs."""

    result = run_watchlist_freshness_monitor()
    logger.info(
        "watchlist_freshness_monitor_completed",
        extra={
            "requested_symbols": result.requested_symbols,
            "checked_symbols": result.checked_symbols,
            "unknown_symbols": result.unknown_symbols,
            "fresh_symbols": result.fresh_symbols,
            "warning_symbols": result.warning_symbols,
            "stale_symbols": result.stale_symbols,
            "missing_symbols": result.missing_symbols,
            "overall_success": result.overall_success,
        },
    )
    print(
        "watchlist_freshness_monitor:"
        f" requested_symbols={result.requested_symbols}"
        f" checked_symbols={result.checked_symbols}"
        f" unknown_symbols={result.unknown_symbols}"
        f" fresh_symbols={result.fresh_symbols}"
        f" warning_symbols={result.warning_symbols}"
        f" stale_symbols={result.stale_symbols}"
        f" missing_symbols={result.missing_symbols}"
        f" overall_success={result.overall_success}"
    )


if __name__ == "__main__":
    main()
