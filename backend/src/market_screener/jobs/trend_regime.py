"""Trend regime classification workflow from indicator snapshots."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.core.trend_regime import (
    TrendRegimeInput,
    classify_trend_regime,
)
from market_screener.db.models.core import Asset, IndicatorSnapshot
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail

logger = logging.getLogger("market_screener.jobs.trend_regime")


@dataclass(frozen=True)
class TrendRegimeAssetStatus:
    """Per-asset trend regime classification status."""

    symbol: str
    asset_id: int
    ts: datetime | None
    regime: str
    confidence: float
    reasons: list[str]


@dataclass(frozen=True)
class TrendRegimeClassificationResult:
    """Summary for one trend regime classification run."""

    requested_assets: int
    classified_assets: int
    missing_indicator_assets: int
    source: str
    statuses: list[TrendRegimeAssetStatus]
    regime_counts: dict[str, int]

    @property
    def overall_success(self) -> bool:
        """True when every requested asset has a classification input row."""

        return self.requested_assets > 0 and self.missing_indicator_assets == 0


class TrendRegimeClassificationJob:
    """Classify latest trend regimes for active assets."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        symbol_limit: int,
        indicator_source: str,
        macd_flat_tolerance: float = 0.10,
    ) -> None:
        self._session_factory = session_factory
        self._symbol_limit = max(1, symbol_limit)
        self._indicator_source = indicator_source.strip() or "ta_v1"
        self._macd_flat_tolerance = max(0.0, macd_flat_tolerance)

    def run(self, *, now_utc: datetime | None = None) -> TrendRegimeClassificationResult:
        """Classify trend regimes from latest indicator snapshots."""

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

        statuses: list[TrendRegimeAssetStatus] = []
        regime_counter: Counter[str] = Counter()
        missing_indicator_assets = 0

        for asset_id, symbol in assets:
            with self._session_factory() as session:
                latest = session.scalar(
                    select(IndicatorSnapshot)
                    .where(
                        IndicatorSnapshot.asset_id == asset_id,
                        IndicatorSnapshot.source == self._indicator_source,
                    )
                    .order_by(IndicatorSnapshot.ts.desc())
                    .limit(1)
                )

            if latest is None:
                missing_indicator_assets += 1
                statuses.append(
                    TrendRegimeAssetStatus(
                        symbol=symbol,
                        asset_id=asset_id,
                        ts=None,
                        regime="unknown",
                        confidence=0.0,
                        reasons=["missing_indicator_snapshot"],
                    )
                )
                regime_counter["unknown"] += 1
                continue

            decision = classify_trend_regime(
                TrendRegimeInput(
                    ts=normalize_to_utc(latest.ts),
                    ma50=_to_float(latest.ma50),
                    ma200=_to_float(latest.ma200),
                    rsi14=_to_float(latest.rsi14),
                    macd=_to_float(latest.macd),
                    macd_signal=_to_float(latest.macd_signal),
                    atr14=_to_float(latest.atr14),
                    bb_upper=_to_float(latest.bb_upper),
                    bb_lower=_to_float(latest.bb_lower),
                ),
                macd_flat_tolerance=self._macd_flat_tolerance,
            )
            statuses.append(
                TrendRegimeAssetStatus(
                    symbol=symbol,
                    asset_id=asset_id,
                    ts=decision.ts,
                    regime=decision.regime,
                    confidence=decision.confidence,
                    reasons=decision.reasons,
                )
            )
            regime_counter[decision.regime] += 1

        return TrendRegimeClassificationResult(
            requested_assets=len(assets),
            classified_assets=len(statuses),
            missing_indicator_assets=missing_indicator_assets,
            source=self._indicator_source,
            statuses=statuses,
            regime_counts=dict(sorted(regime_counter.items())),
        )


def run_trend_regime_classification(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> TrendRegimeClassificationResult:
    """Run trend regime classification with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    job = TrendRegimeClassificationJob(
        resolved_session_factory,
        symbol_limit=resolved_settings.trend_regime_symbol_limit,
        indicator_source=resolved_settings.trend_regime_indicator_source,
        macd_flat_tolerance=resolved_settings.trend_regime_macd_flat_tolerance,
    )

    with resolved_audit.track_job_run(
        "trend_regime_classification",
        details={
            "symbol_limit": resolved_settings.trend_regime_symbol_limit,
            "indicator_source": resolved_settings.trend_regime_indicator_source,
            "macd_flat_tolerance": resolved_settings.trend_regime_macd_flat_tolerance,
        },
    ) as run_handle:
        result = job.run(now_utc=now_utc)
        run_handle.add_details(
            {
                "requested_assets": result.requested_assets,
                "classified_assets": result.classified_assets,
                "missing_indicator_assets": result.missing_indicator_assets,
                "regime_counts": result.regime_counts,
                "overall_success": result.overall_success,
            }
        )
        return result


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def main() -> None:
    """CLI entrypoint for trend regime classification."""

    result = run_trend_regime_classification()
    logger.info(
        "trend_regime_classification_completed",
        extra={
            "requested_assets": result.requested_assets,
            "classified_assets": result.classified_assets,
            "missing_indicator_assets": result.missing_indicator_assets,
            "regime_counts": result.regime_counts,
            "overall_success": result.overall_success,
        },
    )
    print(
        "trend_regime_classification:"
        f" requested_assets={result.requested_assets}"
        f" classified_assets={result.classified_assets}"
        f" missing_indicator_assets={result.missing_indicator_assets}"
        f" regime_counts={result.regime_counts}"
        f" overall_success={result.overall_success}"
    )


if __name__ == "__main__":
    main()
