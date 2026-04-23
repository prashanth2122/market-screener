"""Relative volume calculation workflow from recent OHLCV history."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import logging

from sqlalchemy import select

from market_screener.core.relative_volume import (
    RelativeVolumeInput,
    calculate_relative_volume,
)
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, Price
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail

logger = logging.getLogger("market_screener.jobs.relative_volume")


@dataclass(frozen=True)
class RelativeVolumeAssetStatus:
    """Per-asset relative volume status."""

    symbol: str
    asset_id: int
    ts: datetime | None
    state: str
    ratio: float | None
    current_volume: float | None
    baseline_avg_volume: float | None
    reasons: list[str]


@dataclass(frozen=True)
class RelativeVolumeResult:
    """Summary for one relative volume calculation run."""

    requested_assets: int
    classified_assets: int
    missing_history_assets: int
    state_counts: dict[str, int]
    statuses: list[RelativeVolumeAssetStatus]
    lookback_bars: int
    spike_threshold: float
    dry_up_threshold: float

    @property
    def overall_success(self) -> bool:
        """True when all assets have enough history and current volume."""

        return self.requested_assets > 0 and self.missing_history_assets == 0


class RelativeVolumeJob:
    """Calculate relative volume for active assets."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        symbol_limit: int,
        lookback_bars: int,
        spike_threshold: float,
        dry_up_threshold: float,
    ) -> None:
        self._session_factory = session_factory
        self._symbol_limit = max(1, symbol_limit)
        self._lookback_bars = max(2, lookback_bars)
        self._spike_threshold = max(1.0, spike_threshold)
        self._dry_up_threshold = min(1.0, max(0.0, dry_up_threshold))

    def run(self, *, now_utc: datetime | None = None) -> RelativeVolumeResult:
        """Run relative volume calculations for active assets."""

        _ = normalize_to_utc(now_utc or datetime.now(UTC))

        with self._session_factory() as session:
            assets = list(
                session.execute(
                    select(Asset.id, Asset.symbol)
                    .where(Asset.active.is_(True))
                    .order_by(Asset.symbol.asc())
                    .limit(self._symbol_limit)
                ).all()
            )

        statuses: list[RelativeVolumeAssetStatus] = []
        state_counter: Counter[str] = Counter()
        missing_history_assets = 0

        for asset_id, symbol in assets:
            with self._session_factory() as session:
                rows = list(
                    session.execute(
                        select(Price.ts, Price.volume)
                        .where(Price.asset_id == asset_id)
                        .order_by(Price.ts.desc())
                        .limit(self._lookback_bars)
                    ).all()
                )

            if len(rows) < 2:
                missing_history_assets += 1
                statuses.append(
                    RelativeVolumeAssetStatus(
                        symbol=symbol,
                        asset_id=asset_id,
                        ts=None,
                        state="unknown",
                        ratio=None,
                        current_volume=None,
                        baseline_avg_volume=None,
                        reasons=["insufficient_volume_history"],
                    )
                )
                state_counter["unknown"] += 1
                continue

            latest_ts, latest_volume = rows[0]
            baseline = [float(volume) for _, volume in rows[1:] if volume is not None]
            decision = calculate_relative_volume(
                RelativeVolumeInput(
                    ts=normalize_to_utc(latest_ts),
                    current_volume=(float(latest_volume) if latest_volume is not None else None),
                    baseline_volumes=baseline,
                ),
                spike_threshold=self._spike_threshold,
                dry_up_threshold=self._dry_up_threshold,
            )
            if decision.state == "unknown":
                missing_history_assets += 1
            statuses.append(
                RelativeVolumeAssetStatus(
                    symbol=symbol,
                    asset_id=asset_id,
                    ts=decision.ts,
                    state=decision.state,
                    ratio=decision.ratio,
                    current_volume=decision.current_volume,
                    baseline_avg_volume=decision.baseline_avg_volume,
                    reasons=decision.reasons,
                )
            )
            state_counter[decision.state] += 1

        return RelativeVolumeResult(
            requested_assets=len(assets),
            classified_assets=len(statuses),
            missing_history_assets=missing_history_assets,
            state_counts=dict(sorted(state_counter.items())),
            statuses=statuses,
            lookback_bars=self._lookback_bars,
            spike_threshold=self._spike_threshold,
            dry_up_threshold=self._dry_up_threshold,
        )


def run_relative_volume_calculation(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> RelativeVolumeResult:
    """Run relative volume workflow with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)

    job = RelativeVolumeJob(
        resolved_session_factory,
        symbol_limit=resolved_settings.relative_volume_symbol_limit,
        lookback_bars=resolved_settings.relative_volume_lookback_bars,
        spike_threshold=resolved_settings.relative_volume_spike_threshold,
        dry_up_threshold=resolved_settings.relative_volume_dry_up_threshold,
    )
    with resolved_audit.track_job_run(
        "relative_volume_calculation",
        details={
            "symbol_limit": resolved_settings.relative_volume_symbol_limit,
            "lookback_bars": resolved_settings.relative_volume_lookback_bars,
            "spike_threshold": resolved_settings.relative_volume_spike_threshold,
            "dry_up_threshold": resolved_settings.relative_volume_dry_up_threshold,
        },
    ) as run_handle:
        result = job.run(now_utc=now_utc)
        run_handle.add_details(
            {
                "requested_assets": result.requested_assets,
                "classified_assets": result.classified_assets,
                "missing_history_assets": result.missing_history_assets,
                "state_counts": result.state_counts,
                "overall_success": result.overall_success,
            }
        )
        return result


def main() -> None:
    """CLI entrypoint for relative volume calculation."""

    result = run_relative_volume_calculation()
    logger.info(
        "relative_volume_calculation_completed",
        extra={
            "requested_assets": result.requested_assets,
            "classified_assets": result.classified_assets,
            "missing_history_assets": result.missing_history_assets,
            "state_counts": result.state_counts,
            "overall_success": result.overall_success,
        },
    )
    print(
        "relative_volume_calculation:"
        f" requested_assets={result.requested_assets}"
        f" classified_assets={result.classified_assets}"
        f" missing_history_assets={result.missing_history_assets}"
        f" state_counts={result.state_counts}"
        f" overall_success={result.overall_success}"
    )


if __name__ == "__main__":
    main()
