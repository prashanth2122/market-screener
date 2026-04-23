"""Validation workflow for 7-day historical backfill coverage."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.db.models.core import Asset, Price
from market_screener.db.session import (
    SessionFactory,
    create_session_factory_from_settings,
)
from market_screener.jobs.audit import JobAuditTrail

logger = logging.getLogger("market_screener.jobs.backfill_validation")


@dataclass(frozen=True)
class SymbolBackfillStatus:
    """Per-symbol validation outcome for historical backfill."""

    symbol: str
    row_count: int
    earliest_ts: datetime | None
    latest_ts: datetime | None
    is_backfilled: bool
    failure_reason: str | None = None


@dataclass(frozen=True)
class BackfillValidationResult:
    """Summary for one backfill validation pass."""

    requested_symbols: int
    checked_symbols: int
    lookback_days: int
    window_start: datetime
    window_end: datetime
    passed_symbols: int
    failed_symbols: int
    symbol_statuses: list[SymbolBackfillStatus]

    @property
    def overall_success(self) -> bool:
        """True when all checked symbols satisfy backfill requirements."""

        return self.checked_symbols > 0 and self.failed_symbols == 0


class EquityBackfillValidationJob:
    """Validate recent OHLCV backfill coverage for active equity symbols."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        symbol_limit: int,
        lookback_days: int,
        min_rows: int,
        max_last_row_age_days: int,
        source: str = "finnhub",
    ) -> None:
        self._session_factory = session_factory
        self._symbol_limit = max(1, symbol_limit)
        self._lookback_days = max(1, lookback_days)
        self._min_rows = max(1, min_rows)
        self._max_last_row_age_days = max(1, max_last_row_age_days)
        self._source = source

    def run(self, *, now_utc: datetime | None = None) -> BackfillValidationResult:
        """Run backfill validation for the configured equity sample."""

        window_end = now_utc or datetime.now(UTC)
        if window_end.tzinfo is None:
            window_end = window_end.replace(tzinfo=UTC)
        window_start = window_end - timedelta(days=self._lookback_days)
        freshness_cutoff = window_end - timedelta(days=self._max_last_row_age_days)

        with self._session_factory() as session:
            assets = session.scalars(
                select(Asset)
                .where(Asset.asset_type == "equity", Asset.active.is_(True))
                .order_by(Asset.symbol.asc())
                .limit(self._symbol_limit)
            ).all()

        if not assets:
            return BackfillValidationResult(
                requested_symbols=self._symbol_limit,
                checked_symbols=0,
                lookback_days=self._lookback_days,
                window_start=window_start,
                window_end=window_end,
                passed_symbols=0,
                failed_symbols=0,
                symbol_statuses=[],
            )

        asset_by_id = {asset.id: asset.symbol for asset in assets}
        with self._session_factory() as session:
            rows = session.execute(
                select(Price.asset_id, Price.ts)
                .where(
                    Price.asset_id.in_(list(asset_by_id.keys())),
                    Price.source == self._source,
                    Price.ts >= window_start,
                    Price.ts <= window_end,
                )
                .order_by(Price.asset_id.asc(), Price.ts.asc())
            ).all()

        ts_by_asset: dict[int, list[datetime]] = {asset_id: [] for asset_id in asset_by_id}
        for asset_id, ts in rows:
            normalized_ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts
            ts_by_asset[asset_id].append(normalized_ts)

        statuses: list[SymbolBackfillStatus] = []
        passed_symbols = 0
        failed_symbols = 0

        for asset_id, symbol in sorted(asset_by_id.items(), key=lambda item: item[1]):
            timestamps = ts_by_asset.get(asset_id, [])
            row_count = len(timestamps)
            earliest_ts = timestamps[0] if timestamps else None
            latest_ts = timestamps[-1] if timestamps else None

            failure_reason: str | None = None
            if row_count == 0:
                failure_reason = "missing_rows"
            elif row_count < self._min_rows:
                failure_reason = "insufficient_rows"
            elif latest_ts is not None and latest_ts < freshness_cutoff:
                failure_reason = "stale_latest_row"

            is_backfilled = failure_reason is None
            if is_backfilled:
                passed_symbols += 1
            else:
                failed_symbols += 1

            statuses.append(
                SymbolBackfillStatus(
                    symbol=symbol,
                    row_count=row_count,
                    earliest_ts=earliest_ts,
                    latest_ts=latest_ts,
                    is_backfilled=is_backfilled,
                    failure_reason=failure_reason,
                )
            )

        return BackfillValidationResult(
            requested_symbols=self._symbol_limit,
            checked_symbols=len(statuses),
            lookback_days=self._lookback_days,
            window_start=window_start,
            window_end=window_end,
            passed_symbols=passed_symbols,
            failed_symbols=failed_symbols,
            symbol_statuses=statuses,
        )


def run_equity_backfill_validation(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
) -> BackfillValidationResult:
    """Run equity backfill validation with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)

    job = EquityBackfillValidationJob(
        resolved_session_factory,
        symbol_limit=resolved_settings.backfill_validation_symbol_limit,
        lookback_days=resolved_settings.backfill_validation_lookback_days,
        min_rows=resolved_settings.backfill_validation_min_rows,
        max_last_row_age_days=resolved_settings.backfill_validation_max_last_row_age_days,
    )
    with resolved_audit.track_job_run(
        "equity_backfill_validation",
        details={
            "source": "finnhub",
            "symbol_limit": resolved_settings.backfill_validation_symbol_limit,
            "lookback_days": resolved_settings.backfill_validation_lookback_days,
            "min_rows": resolved_settings.backfill_validation_min_rows,
            "max_last_row_age_days": resolved_settings.backfill_validation_max_last_row_age_days,
        },
    ) as run_handle:
        result = job.run()
        run_handle.add_details(
            {
                "checked_symbols": result.checked_symbols,
                "passed_symbols": result.passed_symbols,
                "failed_symbols": result.failed_symbols,
                "overall_success": result.overall_success,
                "failed_reasons": sorted(
                    {
                        status.failure_reason
                        for status in result.symbol_statuses
                        if status.failure_reason is not None
                    }
                ),
            }
        )
        return result


def main() -> None:
    """CLI entrypoint for backfill validation."""

    result = run_equity_backfill_validation()
    logger.info(
        "equity_backfill_validation_completed",
        extra={
            "checked_symbols": result.checked_symbols,
            "passed_symbols": result.passed_symbols,
            "failed_symbols": result.failed_symbols,
            "overall_success": result.overall_success,
        },
    )
    print(
        "equity_backfill_validation:"
        f" checked_symbols={result.checked_symbols}"
        f" passed_symbols={result.passed_symbols}"
        f" failed_symbols={result.failed_symbols}"
        f" overall_success={result.overall_success}"
    )


if __name__ == "__main__":
    main()
