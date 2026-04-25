"""Asset detail API endpoint with latest model context and recent history."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from market_screener.core.score_factors import SCORE_MODEL_VERSION
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import (
    Asset,
    FundamentalsSnapshot,
    IndicatorSnapshot,
    NewsEvent,
    Price,
    ScoreHistory,
    SignalHistory,
)
from market_screener.db.session import create_session_factory_from_settings

router = APIRouter(tags=["assets"])


@router.get("/{symbol}")
def get_asset_detail(
    symbol: str,
    model_version: str = Query(default=SCORE_MODEL_VERSION),
    price_source: str | None = Query(default=None),
    price_lookback_days: int = Query(default=90, ge=1, le=3650),
    price_limit: int = Query(default=200, ge=1, le=1000),
    indicator_source: str | None = Query(default=None),
    fundamentals_source: str | None = Query(default=None),
    news_source: str | None = Query(default=None),
    news_limit: int = Query(default=20, ge=1, le=100),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Return one-symbol detail context for screener drill-down views."""

    normalized_symbol = (symbol or "").strip().upper()
    if not normalized_symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symbol is required",
        )

    resolved_model_version = (model_version or "").strip() or SCORE_MODEL_VERSION
    resolved_indicator_source = (
        indicator_source or ""
    ).strip() or settings.indicator_snapshot_source
    resolved_fundamentals_source = (
        fundamentals_source or ""
    ).strip() or settings.fundamentals_snapshot_source
    resolved_news_source = (news_source or "").strip() or settings.news_ingestion_source
    resolved_price_source = (price_source or "").strip() or None

    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        asset = session.scalar(
            select(Asset).where(func.upper(Asset.symbol) == normalized_symbol).limit(1)
        )
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"asset not found: {normalized_symbol}",
            )

        latest_signal = session.scalar(
            select(SignalHistory)
            .where(
                SignalHistory.asset_id == asset.id,
                SignalHistory.model_version == resolved_model_version,
            )
            .order_by(SignalHistory.as_of_ts.desc())
            .limit(1)
        )
        latest_score = session.scalar(
            select(ScoreHistory)
            .where(
                ScoreHistory.asset_id == asset.id,
                ScoreHistory.model_version == resolved_model_version,
            )
            .order_by(ScoreHistory.as_of_ts.desc())
            .limit(1)
        )
        latest_indicator = session.scalar(
            select(IndicatorSnapshot)
            .where(
                IndicatorSnapshot.asset_id == asset.id,
                IndicatorSnapshot.source == resolved_indicator_source,
            )
            .order_by(IndicatorSnapshot.ts.desc())
            .limit(1)
        )
        latest_fundamentals = session.scalar(
            select(FundamentalsSnapshot)
            .where(
                FundamentalsSnapshot.asset_id == asset.id,
                FundamentalsSnapshot.source == resolved_fundamentals_source,
            )
            .order_by(
                FundamentalsSnapshot.period_end.desc(),
                FundamentalsSnapshot.as_of_ts.desc(),
            )
            .limit(1)
        )

        price_cutoff = normalize_to_utc(datetime.now(UTC)) - timedelta(days=price_lookback_days)
        price_query = (
            select(Price)
            .where(
                Price.asset_id == asset.id,
                Price.ts >= price_cutoff,
            )
            .order_by(Price.ts.desc())
            .limit(price_limit)
        )
        if resolved_price_source:
            price_query = price_query.where(Price.source == resolved_price_source)
        prices_desc = list(session.scalars(price_query).all())
        prices = list(reversed(prices_desc))

        news_query = (
            select(NewsEvent)
            .where(
                NewsEvent.asset_id == asset.id,
                NewsEvent.source == resolved_news_source,
            )
            .order_by(NewsEvent.published_at.desc())
            .limit(news_limit)
        )
        news_events = list(session.scalars(news_query).all())

    latest_as_of_ts = _max_timestamp(
        latest_signal_as_of=None if latest_signal is None else latest_signal.as_of_ts,
        latest_score_as_of=None if latest_score is None else latest_score.as_of_ts,
        latest_indicator_ts=None if latest_indicator is None else latest_indicator.ts,
        latest_fundamentals_as_of=(
            None if latest_fundamentals is None else latest_fundamentals.as_of_ts
        ),
    )
    return {
        "status": "ok",
        "asset": {
            "symbol": asset.symbol,
            "asset_type": asset.asset_type,
            "exchange": asset.exchange,
            "base_currency": asset.base_currency,
            "quote_currency": asset.quote_currency,
            "active": bool(asset.active),
        },
        "sources": {
            "price_source": resolved_price_source,
            "indicator_source": resolved_indicator_source,
            "fundamentals_source": resolved_fundamentals_source,
            "news_source": resolved_news_source,
            "model_version": resolved_model_version,
        },
        "latest_as_of_ts": (
            None if latest_as_of_ts is None else normalize_to_utc(latest_as_of_ts).isoformat()
        ),
        "latest": {
            "signal": _serialize_signal_row(latest_signal),
            "score": _serialize_score_row(latest_score),
            "indicator": _serialize_indicator_row(latest_indicator),
            "fundamentals": _serialize_fundamentals_row(latest_fundamentals),
        },
        "history": {
            "prices": [_serialize_price_row(row) for row in prices],
            "news": [_serialize_news_row(row) for row in news_events],
        },
        "counts": {
            "prices": len(prices),
            "news": len(news_events),
        },
    }


def _serialize_signal_row(row: SignalHistory | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "as_of_ts": normalize_to_utc(row.as_of_ts).isoformat(),
        "signal": row.signal,
        "score": _to_float(row.score),
        "confidence": _to_float(row.confidence),
        "blocked_by_risk": bool(row.blocked_by_risk),
        "reasons": row.reasons or [],
        "details": row.details or {},
    }


def _serialize_score_row(row: ScoreHistory | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "as_of_ts": normalize_to_utc(row.as_of_ts).isoformat(),
        "composite_score": _to_float(row.composite_score),
        "technical_score": _to_float(row.technical_score),
        "fundamental_score": _to_float(row.fundamental_score),
        "sentiment_risk_score": _to_float(row.sentiment_risk_score),
        "details": row.details or {},
    }


def _serialize_indicator_row(row: IndicatorSnapshot | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "ts": normalize_to_utc(row.ts).isoformat(),
        "source": row.source,
        "ma50": _to_float(row.ma50),
        "ma200": _to_float(row.ma200),
        "rsi14": _to_float(row.rsi14),
        "macd": _to_float(row.macd),
        "macd_signal": _to_float(row.macd_signal),
        "atr14": _to_float(row.atr14),
        "bb_upper": _to_float(row.bb_upper),
        "bb_lower": _to_float(row.bb_lower),
    }


def _serialize_fundamentals_row(row: FundamentalsSnapshot | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "as_of_ts": normalize_to_utc(row.as_of_ts).isoformat(),
        "period_type": row.period_type,
        "period_end": _to_date_iso(row.period_end),
        "filing_date": _to_date_iso(row.filing_date),
        "statement_currency": row.statement_currency,
        "revenue": _to_float(row.revenue),
        "gross_profit": _to_float(row.gross_profit),
        "ebit": _to_float(row.ebit),
        "net_income": _to_float(row.net_income),
        "operating_cash_flow": _to_float(row.operating_cash_flow),
        "total_assets": _to_float(row.total_assets),
        "total_liabilities": _to_float(row.total_liabilities),
        "market_cap": _to_float(row.market_cap),
        "eps_basic": _to_float(row.eps_basic),
        "eps_diluted": _to_float(row.eps_diluted),
        "details": row.details or {},
    }


def _serialize_price_row(row: Price) -> dict[str, object]:
    return {
        "ts": normalize_to_utc(row.ts).isoformat(),
        "source": row.source,
        "open": _to_float(row.open),
        "high": _to_float(row.high),
        "low": _to_float(row.low),
        "close": _to_float(row.close),
        "volume": _to_float(row.volume),
    }


def _serialize_news_row(row: NewsEvent) -> dict[str, object]:
    return {
        "published_at": normalize_to_utc(row.published_at).isoformat(),
        "source": row.source,
        "title": row.title,
        "description": row.description,
        "url": row.url,
        "language": row.language,
        "sentiment_score": _to_float(row.sentiment_score),
        "event_type": row.event_type,
        "risk_flag": row.risk_flag,
        "details": row.details or {},
    }


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_date_iso(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _max_timestamp(
    *,
    latest_signal_as_of: datetime | None,
    latest_score_as_of: datetime | None,
    latest_indicator_ts: datetime | None,
    latest_fundamentals_as_of: datetime | None,
) -> datetime | None:
    candidates = [
        value
        for value in (
            latest_signal_as_of,
            latest_score_as_of,
            latest_indicator_ts,
            latest_fundamentals_as_of,
        )
        if value is not None
    ]
    if not candidates:
        return None
    return max(candidates)
