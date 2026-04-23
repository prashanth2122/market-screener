"""Backfill score and signal history rows for recent windows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from market_screener.core.altman import AltmanFundamentals, compute_altman_z_score
from market_screener.core.composite_score import CompositeScoreInputs, compute_composite_score
from market_screener.core.fundamentals_quality import (
    FundamentalsQualityInputs,
    compute_fundamentals_quality_score,
)
from market_screener.core.growth_metrics import (
    GrowthMetricsFundamentals,
    compute_growth_metrics,
)
from market_screener.core.piotroski import PiotroskiFundamentals, compute_piotroski_f_score
from market_screener.core.score_explanation import build_score_explanation_payload
from market_screener.core.score_factors import (
    SCORE_MODEL_VERSION,
    SentimentRiskFactorInputs,
    TechnicalFactorInputs,
)
from market_screener.core.sentiment import WeightedSentimentArticle, compute_weighted_sentiment
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.core.trend_regime import TrendRegimeInput, classify_trend_regime
from market_screener.core.signal_mapping import map_signal_from_score_explanation
from market_screener.db.models.core import (
    Asset,
    FundamentalsSnapshot,
    IndicatorSnapshot,
    NewsEvent,
    ScoreHistory,
    SignalHistory,
)
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.idempotency import build_idempotency_key

logger = logging.getLogger("market_screener.jobs.score_signal_backfill")


@dataclass(frozen=True)
class ScoreSignalBackfillAssetStatus:
    """Per-asset score/signal backfill status."""

    symbol: str
    snapshot_rows: int
    score_rows_written: int
    signal_rows_written: int
    skipped_existing_rows: int
    failed_rows: int


@dataclass(frozen=True)
class ScoreSignalBackfillResult:
    """Summary for one score/signal backfill run."""

    requested_assets: int
    processed_assets: int
    failed_assets: int
    days_considered: int
    score_rows_written: int
    signal_rows_written: int
    skipped_existing_rows: int
    lookback_days: int
    indicator_source: str
    fundamentals_source: str
    news_source_filter: str | None
    statuses: list[ScoreSignalBackfillAssetStatus]
    idempotent_skip: bool = False


class ScoreSignalBackfillJob:
    """Backfill score and signal history rows over recent indicator windows."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        symbol_limit: int,
        lookback_days: int,
        indicator_source: str,
        fundamentals_source: str,
        news_source_filter: str | None,
        news_lookback_hours: int,
        sentiment_half_life_hours: int,
    ) -> None:
        self._session_factory = session_factory
        self._symbol_limit = max(1, symbol_limit)
        self._lookback_days = max(1, lookback_days)
        self._indicator_source = (indicator_source or "").strip() or "ta_v1"
        self._fundamentals_source = (fundamentals_source or "").strip() or "fmp_v1"
        normalized_news_source = (news_source_filter or "").strip()
        self._news_source_filter = normalized_news_source or None
        self._news_lookback_hours = max(1, news_lookback_hours)
        self._sentiment_half_life_hours = max(1, sentiment_half_life_hours)

    def run(self, *, now_utc: datetime | None = None) -> ScoreSignalBackfillResult:
        """Run score/signal history backfill."""

        reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
        cutoff = reference_now - timedelta(days=self._lookback_days)

        with self._session_factory() as session:
            assets = list(
                session.scalars(
                    select(Asset)
                    .where(Asset.active.is_(True))
                    .order_by(Asset.symbol.asc())
                    .limit(self._symbol_limit)
                ).all()
            )

        processed_assets = 0
        failed_assets = 0
        days_considered = 0
        score_rows_written = 0
        signal_rows_written = 0
        skipped_existing_rows = 0
        statuses: list[ScoreSignalBackfillAssetStatus] = []

        with self._session_factory() as session:
            for asset in assets:
                try:
                    snapshots = list(
                        session.scalars(
                            select(IndicatorSnapshot)
                            .where(
                                IndicatorSnapshot.asset_id == asset.id,
                                IndicatorSnapshot.source == self._indicator_source,
                                IndicatorSnapshot.ts >= cutoff,
                                IndicatorSnapshot.ts <= reference_now,
                            )
                            .order_by(IndicatorSnapshot.ts.asc())
                        ).all()
                    )

                    asset_score_written = 0
                    asset_signal_written = 0
                    asset_skipped = 0
                    asset_failed_rows = 0

                    for snapshot in snapshots:
                        as_of_ts = normalize_to_utc(snapshot.ts)
                        days_considered += 1

                        score_exists = session.scalar(
                            select(ScoreHistory.id)
                            .where(
                                ScoreHistory.asset_id == asset.id,
                                ScoreHistory.as_of_ts == as_of_ts,
                                ScoreHistory.model_version == SCORE_MODEL_VERSION,
                            )
                            .limit(1)
                        )
                        signal_exists = session.scalar(
                            select(SignalHistory.id)
                            .where(
                                SignalHistory.asset_id == asset.id,
                                SignalHistory.as_of_ts == as_of_ts,
                                SignalHistory.model_version == SCORE_MODEL_VERSION,
                            )
                            .limit(1)
                        )
                        if score_exists is not None and signal_exists is not None:
                            skipped_existing_rows += 1
                            asset_skipped += 1
                            continue

                        try:
                            technical_inputs = _build_technical_inputs(snapshot)
                            fundamentals_quality_score = _derive_fundamentals_quality_score(
                                session=session,
                                asset_id=asset.id,
                                as_of_date=as_of_ts.date(),
                                fundamentals_source=self._fundamentals_source,
                            )
                            sentiment_risk_inputs = _derive_sentiment_risk_inputs(
                                session=session,
                                asset_id=asset.id,
                                as_of_ts=as_of_ts,
                                news_source_filter=self._news_source_filter,
                                news_lookback_hours=self._news_lookback_hours,
                                sentiment_half_life_hours=self._sentiment_half_life_hours,
                            )
                            composite = compute_composite_score(
                                CompositeScoreInputs(
                                    asset_symbol=asset.symbol,
                                    as_of_ts=as_of_ts,
                                    technical_inputs=technical_inputs,
                                    fundamentals_quality_score=fundamentals_quality_score,
                                    sentiment_risk_inputs=sentiment_risk_inputs,
                                )
                            )
                            explanation = build_score_explanation_payload(composite).payload
                            signal = map_signal_from_score_explanation(explanation)
                        except Exception:
                            asset_failed_rows += 1
                            logger.exception(
                                "score_signal_backfill_snapshot_failed",
                                extra={
                                    "asset_id": asset.id,
                                    "symbol": asset.symbol,
                                    "as_of_ts": as_of_ts.isoformat(),
                                },
                            )
                            continue

                        if score_exists is None and composite.score is not None:
                            session.add(
                                ScoreHistory(
                                    asset_id=asset.id,
                                    as_of_ts=as_of_ts,
                                    model_version=composite.model_version,
                                    composite_score=_to_decimal(composite.score),
                                    technical_score=_to_decimal(
                                        composite.component_scores.get("technical_strength")
                                    ),
                                    fundamental_score=_to_decimal(
                                        composite.component_scores.get("fundamental_quality")
                                    ),
                                    sentiment_risk_score=_to_decimal(
                                        composite.component_scores.get("sentiment_event_risk")
                                    ),
                                    details={
                                        "effective_weights": composite.effective_weights,
                                        "unavailable_components": composite.unavailable_components,
                                    },
                                )
                            )
                            score_rows_written += 1
                            asset_score_written += 1

                        if signal_exists is None:
                            session.add(
                                SignalHistory(
                                    asset_id=asset.id,
                                    as_of_ts=as_of_ts,
                                    model_version=composite.model_version,
                                    signal=signal.signal,
                                    score=_to_decimal(signal.score),
                                    confidence=_to_decimal(signal.confidence),
                                    blocked_by_risk=signal.blocked_by_risk,
                                    reasons=signal.reasons,
                                    details={
                                        "label": signal.label,
                                        "score_band": explanation.get("score_band"),
                                    },
                                )
                            )
                            signal_rows_written += 1
                            asset_signal_written += 1

                    statuses.append(
                        ScoreSignalBackfillAssetStatus(
                            symbol=asset.symbol,
                            snapshot_rows=len(snapshots),
                            score_rows_written=asset_score_written,
                            signal_rows_written=asset_signal_written,
                            skipped_existing_rows=asset_skipped,
                            failed_rows=asset_failed_rows,
                        )
                    )
                    processed_assets += 1
                except Exception:
                    failed_assets += 1
                    logger.exception(
                        "score_signal_backfill_asset_failed",
                        extra={"asset_id": asset.id, "symbol": asset.symbol},
                    )
                    continue

            session.commit()

        return ScoreSignalBackfillResult(
            requested_assets=len(assets),
            processed_assets=processed_assets,
            failed_assets=failed_assets,
            days_considered=days_considered,
            score_rows_written=score_rows_written,
            signal_rows_written=signal_rows_written,
            skipped_existing_rows=skipped_existing_rows,
            lookback_days=self._lookback_days,
            indicator_source=self._indicator_source,
            fundamentals_source=self._fundamentals_source,
            news_source_filter=self._news_source_filter,
            statuses=statuses,
        )


def run_score_signal_backfill(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> ScoreSignalBackfillResult:
    """Run score/signal history backfill with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    window_anchor_day = reference_now.strftime("%Y-%m-%d")
    symbol_fingerprint = _active_symbol_fingerprint(resolved_session_factory)

    idempotency_key = build_idempotency_key(
        "score_signal_backfill",
        {
            "symbol_limit": resolved_settings.score_backfill_symbol_limit,
            "lookback_days": resolved_settings.score_backfill_lookback_days,
            "indicator_source": resolved_settings.score_backfill_indicator_source,
            "fundamentals_source": resolved_settings.score_backfill_fundamentals_source,
            "news_source_filter": resolved_settings.score_backfill_news_source_filter,
            "news_lookback_hours": resolved_settings.score_backfill_news_lookback_hours,
            "sentiment_half_life_hours": resolved_settings.score_backfill_sentiment_half_life_hours,
            "window_anchor_day": window_anchor_day,
            "symbol_fingerprint": symbol_fingerprint,
            "model_version": SCORE_MODEL_VERSION,
        },
    )

    if resolved_audit.has_completed_run("score_signal_backfill", idempotency_key):
        return ScoreSignalBackfillResult(
            requested_assets=0,
            processed_assets=0,
            failed_assets=0,
            days_considered=0,
            score_rows_written=0,
            signal_rows_written=0,
            skipped_existing_rows=0,
            lookback_days=resolved_settings.score_backfill_lookback_days,
            indicator_source=resolved_settings.score_backfill_indicator_source,
            fundamentals_source=resolved_settings.score_backfill_fundamentals_source,
            news_source_filter=(resolved_settings.score_backfill_news_source_filter or "").strip()
            or None,
            statuses=[],
            idempotent_skip=True,
        )

    job = ScoreSignalBackfillJob(
        resolved_session_factory,
        symbol_limit=resolved_settings.score_backfill_symbol_limit,
        lookback_days=resolved_settings.score_backfill_lookback_days,
        indicator_source=resolved_settings.score_backfill_indicator_source,
        fundamentals_source=resolved_settings.score_backfill_fundamentals_source,
        news_source_filter=resolved_settings.score_backfill_news_source_filter,
        news_lookback_hours=resolved_settings.score_backfill_news_lookback_hours,
        sentiment_half_life_hours=resolved_settings.score_backfill_sentiment_half_life_hours,
    )

    with resolved_audit.track_job_run(
        "score_signal_backfill",
        details={
            "symbol_limit": resolved_settings.score_backfill_symbol_limit,
            "lookback_days": resolved_settings.score_backfill_lookback_days,
            "indicator_source": resolved_settings.score_backfill_indicator_source,
            "fundamentals_source": resolved_settings.score_backfill_fundamentals_source,
            "news_source_filter": resolved_settings.score_backfill_news_source_filter,
            "news_lookback_hours": resolved_settings.score_backfill_news_lookback_hours,
            "sentiment_half_life_hours": resolved_settings.score_backfill_sentiment_half_life_hours,
            "window_anchor_day": window_anchor_day,
            "symbol_fingerprint": symbol_fingerprint,
            "idempotency_key": idempotency_key,
            "idempotency_hit": False,
        },
        idempotency_key=idempotency_key,
    ) as run_handle:
        result = job.run(now_utc=reference_now)
        run_handle.add_details(
            {
                "requested_assets": result.requested_assets,
                "processed_assets": result.processed_assets,
                "failed_assets": result.failed_assets,
                "days_considered": result.days_considered,
                "score_rows_written": result.score_rows_written,
                "signal_rows_written": result.signal_rows_written,
                "skipped_existing_rows": result.skipped_existing_rows,
                "idempotent_skip": False,
            }
        )
        return result


def _build_technical_inputs(snapshot: IndicatorSnapshot) -> TechnicalFactorInputs:
    decision = classify_trend_regime(
        TrendRegimeInput(
            ts=normalize_to_utc(snapshot.ts),
            ma50=_to_float(snapshot.ma50),
            ma200=_to_float(snapshot.ma200),
            rsi14=_to_float(snapshot.rsi14),
            macd=_to_float(snapshot.macd),
            macd_signal=_to_float(snapshot.macd_signal),
            atr14=_to_float(snapshot.atr14),
            bb_upper=_to_float(snapshot.bb_upper),
            bb_lower=_to_float(snapshot.bb_lower),
        )
    )
    return TechnicalFactorInputs(
        trend_regime=decision.regime,
        trend_confidence=decision.confidence,
        breakout_signal=None,
        breakout_confidence=None,
        relative_volume_state=None,
        relative_volume_ratio=None,
    )


def _derive_fundamentals_quality_score(
    *,
    session,
    asset_id: int,
    as_of_date: date,
    fundamentals_source: str,
) -> float | None:
    rows = list(
        session.scalars(
            select(FundamentalsSnapshot)
            .where(
                FundamentalsSnapshot.asset_id == asset_id,
                FundamentalsSnapshot.source == fundamentals_source,
                FundamentalsSnapshot.period_end <= as_of_date,
            )
            .order_by(FundamentalsSnapshot.period_end.desc())
            .limit(2)
        ).all()
    )
    if not rows:
        return None

    current = rows[0]
    previous = rows[1] if len(rows) > 1 else None

    altman = compute_altman_z_score(
        AltmanFundamentals(
            period_end=current.period_end,
            total_assets=_to_float(current.total_assets),
            current_assets=_to_float(current.current_assets),
            current_liabilities=_to_float(current.current_liabilities),
            retained_earnings=_to_float(current.retained_earnings),
            ebit=_to_float(current.ebit),
            market_cap=_to_float(current.market_cap),
            total_liabilities=_to_float(current.total_liabilities),
            revenue=_to_float(current.revenue),
        )
    )

    piotroski_score: int | None = None
    growth_eps_percent: float | None = None
    growth_revenue_percent: float | None = None
    if previous is not None:
        piotroski = compute_piotroski_f_score(
            PiotroskiFundamentals(
                period_end=current.period_end,
                net_income=_to_float(current.net_income),
                operating_cash_flow=_to_float(current.operating_cash_flow),
                total_assets=_to_float(current.total_assets),
                long_term_debt=_to_float(current.long_term_debt),
                current_assets=_to_float(current.current_assets),
                current_liabilities=_to_float(current.current_liabilities),
                shares_outstanding=_to_float(current.shares_outstanding),
                gross_profit=_to_float(current.gross_profit),
                revenue=_to_float(current.revenue),
            ),
            PiotroskiFundamentals(
                period_end=previous.period_end,
                net_income=_to_float(previous.net_income),
                operating_cash_flow=_to_float(previous.operating_cash_flow),
                total_assets=_to_float(previous.total_assets),
                long_term_debt=_to_float(previous.long_term_debt),
                current_assets=_to_float(previous.current_assets),
                current_liabilities=_to_float(previous.current_liabilities),
                shares_outstanding=_to_float(previous.shares_outstanding),
                gross_profit=_to_float(previous.gross_profit),
                revenue=_to_float(previous.revenue),
            ),
        )
        piotroski_score = piotroski.score

        growth = compute_growth_metrics(
            GrowthMetricsFundamentals(
                period_end=current.period_end,
                eps_basic=_to_float(current.eps_basic),
                eps_diluted=_to_float(current.eps_diluted),
                revenue=_to_float(current.revenue),
            ),
            GrowthMetricsFundamentals(
                period_end=previous.period_end,
                eps_basic=_to_float(previous.eps_basic),
                eps_diluted=_to_float(previous.eps_diluted),
                revenue=_to_float(previous.revenue),
            ),
        )
        growth_eps_percent = growth.eps_growth_percent
        growth_revenue_percent = growth.revenue_growth_percent

    total_assets = _to_float(current.total_assets)
    net_income = _to_float(current.net_income)
    total_liabilities = _to_float(current.total_liabilities)
    roe = None
    if total_assets is not None and net_income is not None and total_assets > 0:
        roe = net_income / total_assets

    debt_to_equity = None
    if total_assets is not None and total_liabilities is not None:
        equity = total_assets - total_liabilities
        if equity > 0:
            debt_to_equity = total_liabilities / equity

    quality = compute_fundamentals_quality_score(
        FundamentalsQualityInputs(
            period_end=current.period_end,
            piotroski_score=piotroski_score,
            altman_z_score=altman.z_score,
            altman_zone=altman.zone,
            eps_growth_percent=growth_eps_percent,
            revenue_growth_percent=growth_revenue_percent,
            roe=roe,
            debt_to_equity=debt_to_equity,
        )
    )
    return quality.score


def _derive_sentiment_risk_inputs(
    *,
    session,
    asset_id: int,
    as_of_ts: datetime,
    news_source_filter: str | None,
    news_lookback_hours: int,
    sentiment_half_life_hours: int,
) -> SentimentRiskFactorInputs | None:
    cutoff = as_of_ts - timedelta(hours=news_lookback_hours)
    query = select(NewsEvent).where(
        NewsEvent.asset_id == asset_id,
        NewsEvent.published_at >= cutoff,
        NewsEvent.published_at <= as_of_ts,
    )
    if news_source_filter:
        query = query.where(NewsEvent.source == news_source_filter)
    rows = list(session.scalars(query.order_by(NewsEvent.published_at.desc())).all())
    if not rows:
        return None

    aggregate = compute_weighted_sentiment(
        [
            WeightedSentimentArticle(
                published_at=normalize_to_utc(row.published_at),
                score=_to_float(row.sentiment_score),
            )
            for row in rows
        ],
        now_utc=as_of_ts,
        lookback_hours=news_lookback_hours,
        half_life_hours=sentiment_half_life_hours,
    )

    selected_event = next((row for row in rows if row.risk_flag is True), None)
    if selected_event is None:
        selected_event = next((row for row in rows if row.event_type is not None), None)

    return SentimentRiskFactorInputs(
        weighted_sentiment=aggregate.weighted_sentiment,
        normalized_sentiment_score=aggregate.normalized_score,
        event_type=None if selected_event is None else selected_event.event_type,
        risk_flag=False if selected_event is None else bool(selected_event.risk_flag),
    )


def _active_symbol_fingerprint(session_factory: SessionFactory) -> str:
    with session_factory() as session:
        symbols = sorted(session.scalars(select(Asset.symbol).where(Asset.active.is_(True))).all())
    if not symbols:
        return "none"
    return "|".join(symbols)


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(f"{value:.4f}")
    except (InvalidOperation, ValueError):
        return None


def main() -> None:
    """CLI entrypoint for score/signal history backfill."""

    result = run_score_signal_backfill()
    logger.info(
        "score_signal_backfill_completed",
        extra={
            "requested_assets": result.requested_assets,
            "processed_assets": result.processed_assets,
            "failed_assets": result.failed_assets,
            "days_considered": result.days_considered,
            "score_rows_written": result.score_rows_written,
            "signal_rows_written": result.signal_rows_written,
            "skipped_existing_rows": result.skipped_existing_rows,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "score_signal_backfill:"
        f" requested_assets={result.requested_assets}"
        f" processed_assets={result.processed_assets}"
        f" failed_assets={result.failed_assets}"
        f" days_considered={result.days_considered}"
        f" score_rows_written={result.score_rows_written}"
        f" signal_rows_written={result.signal_rows_written}"
        f" skipped_existing_rows={result.skipped_existing_rows}"
        f" idempotent_skip={result.idempotent_skip}"
    )


if __name__ == "__main__":
    main()
