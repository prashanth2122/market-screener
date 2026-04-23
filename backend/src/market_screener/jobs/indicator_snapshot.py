"""Indicator snapshot persistence workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any

from sqlalchemy import select

from market_screener.core.indicators import ClosePricePoint, calculate_ma50_ma200_rsi14
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, IndicatorSnapshot as IndicatorSnapshotRow, Price
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail

logger = logging.getLogger("market_screener.jobs.indicator_snapshot")


@dataclass(frozen=True)
class IndicatorSnapshotWriteResult:
    """Summary for one indicator snapshot write run."""

    requested_assets: int
    processed_assets: int
    failed_assets: int
    snapshots_written: int
    snapshots_skipped: int
    snapshot_source: str

    @property
    def overall_success(self) -> bool:
        """True when no assets failed during indicator snapshot writes."""

        return self.failed_assets == 0 and self.processed_assets > 0


class IndicatorSnapshotJob:
    """Compute and persist indicator snapshots from stored OHLCV prices."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        symbol_limit: int,
        price_lookback_rows: int,
        snapshot_source: str,
        ta_engine: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._symbol_limit = max(1, symbol_limit)
        self._price_lookback_rows = max(1, price_lookback_rows)
        self._snapshot_source = snapshot_source.strip() or "ta_v1"
        self._ta_engine = ta_engine

    def run(self, *, now_utc: datetime | None = None) -> IndicatorSnapshotWriteResult:
        """Write indicator snapshots for active assets."""

        _ = normalize_to_utc(now_utc or datetime.now(UTC))
        requested_assets = 0
        processed_assets = 0
        failed_assets = 0
        snapshots_written = 0
        snapshots_skipped = 0

        with self._session_factory() as session:
            assets = session.execute(
                select(Asset.id, Asset.symbol)
                .where(Asset.active.is_(True))
                .order_by(Asset.symbol.asc())
                .limit(self._symbol_limit)
            ).all()
        requested_assets = len(assets)

        for asset_id, symbol in assets:
            try:
                with self._session_factory() as session:
                    rows = list(
                        session.execute(
                            select(Price.ts, Price.close, Price.high, Price.low)
                            .where(Price.asset_id == asset_id)
                            .order_by(Price.ts.desc())
                            .limit(self._price_lookback_rows)
                        ).all()
                    )
                    if not rows:
                        processed_assets += 1
                        continue

                    points = [
                        ClosePricePoint(
                            ts=normalize_to_utc(ts),
                            close=close,
                            high=high,
                            low=low,
                        )
                        for ts, close, high, low in reversed(rows)
                    ]
                    indicator_snapshots = calculate_ma50_ma200_rsi14(
                        points, ta_engine=self._ta_engine
                    )
                    written, skipped = self._persist_snapshots(
                        session,
                        asset_id=asset_id,
                        snapshots=indicator_snapshots,
                    )
                    session.commit()
                    snapshots_written += written
                    snapshots_skipped += skipped
                    processed_assets += 1
            except Exception:
                failed_assets += 1
                logger.exception(
                    "indicator_snapshot_asset_failed",
                    extra={
                        "asset_id": asset_id,
                        "symbol": symbol,
                    },
                )

        return IndicatorSnapshotWriteResult(
            requested_assets=requested_assets,
            processed_assets=processed_assets,
            failed_assets=failed_assets,
            snapshots_written=snapshots_written,
            snapshots_skipped=snapshots_skipped,
            snapshot_source=self._snapshot_source,
        )

    def _persist_snapshots(
        self,
        session: Any,
        *,
        asset_id: int,
        snapshots: list[Any],
    ) -> tuple[int, int]:
        if not snapshots:
            return 0, 0

        ts_values = [normalize_to_utc(item.ts) for item in snapshots]
        existing_timestamps = {
            normalize_to_utc(ts)
            for ts in session.scalars(
                select(IndicatorSnapshotRow.ts).where(
                    IndicatorSnapshotRow.asset_id == asset_id,
                    IndicatorSnapshotRow.source == self._snapshot_source,
                    IndicatorSnapshotRow.ts.in_(ts_values),
                )
            ).all()
        }

        written = 0
        skipped = 0
        for item in snapshots:
            snapshot_ts = normalize_to_utc(item.ts)
            if snapshot_ts in existing_timestamps:
                skipped += 1
                continue

            session.add(
                IndicatorSnapshotRow(
                    asset_id=asset_id,
                    ts=snapshot_ts,
                    ma50=_to_decimal(item.ma50),
                    ma200=_to_decimal(item.ma200),
                    rsi14=_to_decimal(item.rsi14),
                    macd=_to_decimal(item.macd),
                    macd_signal=_to_decimal(item.macd_signal),
                    atr14=_to_decimal(item.atr14),
                    bb_upper=_to_decimal(item.bb_upper),
                    bb_lower=_to_decimal(item.bb_lower),
                    source=self._snapshot_source,
                )
            )
            existing_timestamps.add(snapshot_ts)
            written += 1

        return written, skipped


def run_indicator_snapshot_refresh(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> IndicatorSnapshotWriteResult:
    """Run indicator snapshot writes with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)

    job = IndicatorSnapshotJob(
        resolved_session_factory,
        symbol_limit=resolved_settings.indicator_snapshot_symbol_limit,
        price_lookback_rows=resolved_settings.indicator_snapshot_price_lookback_rows,
        snapshot_source=resolved_settings.indicator_snapshot_source,
    )
    with resolved_audit.track_job_run(
        "indicator_snapshot_refresh",
        details={
            "symbol_limit": resolved_settings.indicator_snapshot_symbol_limit,
            "price_lookback_rows": resolved_settings.indicator_snapshot_price_lookback_rows,
            "snapshot_source": resolved_settings.indicator_snapshot_source,
        },
    ) as run_handle:
        result = job.run(now_utc=now_utc)
        run_handle.add_details(
            {
                "requested_assets": result.requested_assets,
                "processed_assets": result.processed_assets,
                "failed_assets": result.failed_assets,
                "snapshots_written": result.snapshots_written,
                "snapshots_skipped": result.snapshots_skipped,
                "overall_success": result.overall_success,
                "snapshot_source": result.snapshot_source,
            }
        )
        return result


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def main() -> None:
    """CLI entrypoint for indicator snapshot refresh."""

    result = run_indicator_snapshot_refresh()
    logger.info(
        "indicator_snapshot_refresh_completed",
        extra={
            "requested_assets": result.requested_assets,
            "processed_assets": result.processed_assets,
            "failed_assets": result.failed_assets,
            "snapshots_written": result.snapshots_written,
            "snapshots_skipped": result.snapshots_skipped,
            "snapshot_source": result.snapshot_source,
            "overall_success": result.overall_success,
        },
    )
    print(
        "indicator_snapshot_refresh:"
        f" requested_assets={result.requested_assets}"
        f" processed_assets={result.processed_assets}"
        f" failed_assets={result.failed_assets}"
        f" snapshots_written={result.snapshots_written}"
        f" snapshots_skipped={result.snapshots_skipped}"
        f" snapshot_source={result.snapshot_source}"
        f" overall_success={result.overall_success}"
    )


if __name__ == "__main__":
    main()
