"""Breakout detection workflow from recent price structure."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from sqlalchemy import select

from market_screener.core.breakout import BreakoutInput, detect_breakout
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, IndicatorSnapshot, Price
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail

logger = logging.getLogger("market_screener.jobs.breakout_detection")


@dataclass(frozen=True)
class BreakoutAssetStatus:
    """Per-asset breakout detection status."""

    symbol: str
    asset_id: int
    ts: datetime | None
    signal: str
    confidence: float
    reasons: list[str]
    close: float | None
    recent_high: float | None
    recent_low: float | None


@dataclass(frozen=True)
class BreakoutDetectionResult:
    """Summary for one breakout detection run."""

    requested_assets: int
    classified_assets: int
    missing_history_assets: int
    breakout_counts: dict[str, int]
    statuses: list[BreakoutAssetStatus]
    breakout_buffer_ratio: float
    lookback_bars: int

    @property
    def overall_success(self) -> bool:
        """True when all requested assets have enough history for classification."""

        return self.requested_assets > 0 and self.missing_history_assets == 0


class BreakoutDetectionJob:
    """Detect breakout states for active assets."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        symbol_limit: int,
        lookback_bars: int,
        breakout_buffer_ratio: float,
        indicator_source: str,
    ) -> None:
        self._session_factory = session_factory
        self._symbol_limit = max(1, symbol_limit)
        self._lookback_bars = max(2, lookback_bars)
        self._breakout_buffer_ratio = max(0.0, breakout_buffer_ratio)
        self._indicator_source = indicator_source.strip() or "ta_v1"

    def run(self, *, now_utc: datetime | None = None) -> BreakoutDetectionResult:
        """Run breakout detection for active assets."""

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

        statuses: list[BreakoutAssetStatus] = []
        breakout_counter: Counter[str] = Counter()
        missing_history_assets = 0

        for asset_id, symbol in assets:
            with self._session_factory() as session:
                rows = list(
                    session.execute(
                        select(Price.ts, Price.close, Price.high, Price.low)
                        .where(Price.asset_id == asset_id)
                        .order_by(Price.ts.desc())
                        .limit(self._lookback_bars)
                    ).all()
                )

                latest_indicator = session.scalar(
                    select(IndicatorSnapshot)
                    .where(
                        IndicatorSnapshot.asset_id == asset_id,
                        IndicatorSnapshot.source == self._indicator_source,
                    )
                    .order_by(IndicatorSnapshot.ts.desc())
                    .limit(1)
                )

            if len(rows) < 2:
                missing_history_assets += 1
                statuses.append(
                    BreakoutAssetStatus(
                        symbol=symbol,
                        asset_id=asset_id,
                        ts=None,
                        signal="unknown",
                        confidence=0.0,
                        reasons=["insufficient_price_history"],
                        close=None,
                        recent_high=None,
                        recent_low=None,
                    )
                )
                breakout_counter["unknown"] += 1
                continue

            latest_ts, latest_close, latest_high, latest_low = rows[0]
            previous = rows[1:]
            recent_high = max(float(price_high) for _, _, price_high, _ in previous)
            recent_low = min(float(price_low) for _, _, _, price_low in previous)
            input_point = BreakoutInput(
                ts=normalize_to_utc(latest_ts),
                close=float(latest_close),
                high=float(latest_high),
                low=float(latest_low),
                recent_high=recent_high,
                recent_low=recent_low,
                bb_upper=_to_float(latest_indicator.bb_upper if latest_indicator else None),
                bb_lower=_to_float(latest_indicator.bb_lower if latest_indicator else None),
                atr14=_to_float(latest_indicator.atr14 if latest_indicator else None),
            )
            decision = detect_breakout(
                input_point,
                breakout_buffer_ratio=self._breakout_buffer_ratio,
            )
            statuses.append(
                BreakoutAssetStatus(
                    symbol=symbol,
                    asset_id=asset_id,
                    ts=decision.ts,
                    signal=decision.signal,
                    confidence=decision.confidence,
                    reasons=decision.reasons,
                    close=input_point.close,
                    recent_high=recent_high,
                    recent_low=recent_low,
                )
            )
            breakout_counter[decision.signal] += 1

        return BreakoutDetectionResult(
            requested_assets=len(assets),
            classified_assets=len(statuses),
            missing_history_assets=missing_history_assets,
            breakout_counts=dict(sorted(breakout_counter.items())),
            statuses=statuses,
            breakout_buffer_ratio=self._breakout_buffer_ratio,
            lookback_bars=self._lookback_bars,
        )


def run_breakout_detection(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> BreakoutDetectionResult:
    """Run breakout detection with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    job = BreakoutDetectionJob(
        resolved_session_factory,
        symbol_limit=resolved_settings.breakout_symbol_limit,
        lookback_bars=resolved_settings.breakout_lookback_bars,
        breakout_buffer_ratio=resolved_settings.breakout_buffer_ratio,
        indicator_source=resolved_settings.breakout_indicator_source,
    )
    with resolved_audit.track_job_run(
        "breakout_detection",
        details={
            "symbol_limit": resolved_settings.breakout_symbol_limit,
            "lookback_bars": resolved_settings.breakout_lookback_bars,
            "breakout_buffer_ratio": resolved_settings.breakout_buffer_ratio,
            "indicator_source": resolved_settings.breakout_indicator_source,
        },
    ) as run_handle:
        result = job.run(now_utc=now_utc)
        run_handle.add_details(
            {
                "requested_assets": result.requested_assets,
                "classified_assets": result.classified_assets,
                "missing_history_assets": result.missing_history_assets,
                "breakout_counts": result.breakout_counts,
                "overall_success": result.overall_success,
            }
        )
        return result


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def main() -> None:
    """CLI entrypoint for breakout detection."""

    result = run_breakout_detection()
    logger.info(
        "breakout_detection_completed",
        extra={
            "requested_assets": result.requested_assets,
            "classified_assets": result.classified_assets,
            "missing_history_assets": result.missing_history_assets,
            "breakout_counts": result.breakout_counts,
            "overall_success": result.overall_success,
        },
    )
    print(
        "breakout_detection:"
        f" requested_assets={result.requested_assets}"
        f" classified_assets={result.classified_assets}"
        f" missing_history_assets={result.missing_history_assets}"
        f" breakout_counts={result.breakout_counts}"
        f" overall_success={result.overall_success}"
    )


if __name__ == "__main__":
    main()
