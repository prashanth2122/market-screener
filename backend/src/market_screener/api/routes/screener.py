"""Screener API endpoint with filters for latest model outputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select

from market_screener.core.score_factors import SCORE_MODEL_VERSION
from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, ScoreHistory, SignalHistory
from market_screener.db.session import create_session_factory_from_settings

router = APIRouter(tags=["screener"])

_SORT_FIELDS = {
    "score": "score",
    "confidence": "confidence",
    "symbol": "symbol",
    "as_of_ts": "as_of_ts",
    "signal": "signal",
}


@router.get("")
def get_screener(
    asset_types: str | None = Query(
        default=None,
        description="Comma-separated asset types (for example: equity,crypto).",
    ),
    exchanges: str | None = Query(
        default=None,
        description="Comma-separated exchanges (for example: US,NSE,GLOBAL).",
    ),
    quote_currencies: str | None = Query(
        default=None,
        description="Comma-separated quote currencies (for example: USD,INR).",
    ),
    signals: str | None = Query(
        default=None,
        description="Comma-separated signal filters (strong_buy,buy,watch,avoid).",
    ),
    symbol_query: str | None = Query(
        default=None,
        description="Case-insensitive symbol partial match.",
    ),
    min_score: float | None = Query(default=None),
    max_score: float | None = Query(default=None),
    min_confidence: float | None = Query(default=None),
    blocked_by_risk: bool | None = Query(default=None),
    model_version: str = Query(default=SCORE_MODEL_VERSION),
    sort_by: Literal["score", "confidence", "symbol", "as_of_ts", "signal"] = Query(
        default="score",
    ),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Return latest screener rows with filtering and pagination."""

    parsed_asset_types = _parse_csv_filter(asset_types)
    parsed_exchanges = _parse_csv_filter(exchanges)
    parsed_quote_currencies = _parse_csv_filter(quote_currencies)
    parsed_signals = _parse_csv_filter(signals)
    parsed_model_version = (model_version or "").strip() or SCORE_MODEL_VERSION
    parsed_symbol_query = (symbol_query or "").strip().lower()

    session_factory = create_session_factory_from_settings(settings)
    with session_factory() as session:
        latest_signal_subquery = (
            select(
                SignalHistory.asset_id.label("asset_id"),
                func.max(SignalHistory.as_of_ts).label("latest_as_of_ts"),
            )
            .where(SignalHistory.model_version == parsed_model_version)
            .group_by(SignalHistory.asset_id)
            .subquery()
        )

        score_value = func.coalesce(SignalHistory.score, ScoreHistory.composite_score)
        base_query = (
            select(Asset, SignalHistory, ScoreHistory, score_value.label("score_value"))
            .join(latest_signal_subquery, latest_signal_subquery.c.asset_id == Asset.id)
            .join(
                SignalHistory,
                and_(
                    SignalHistory.asset_id == latest_signal_subquery.c.asset_id,
                    SignalHistory.as_of_ts == latest_signal_subquery.c.latest_as_of_ts,
                    SignalHistory.model_version == parsed_model_version,
                ),
            )
            .outerjoin(
                ScoreHistory,
                and_(
                    ScoreHistory.asset_id == SignalHistory.asset_id,
                    ScoreHistory.as_of_ts == SignalHistory.as_of_ts,
                    ScoreHistory.model_version == SignalHistory.model_version,
                ),
            )
            .where(Asset.active.is_(True))
        )

        if parsed_asset_types:
            base_query = base_query.where(func.lower(Asset.asset_type).in_(parsed_asset_types))
        if parsed_exchanges:
            base_query = base_query.where(func.lower(Asset.exchange).in_(parsed_exchanges))
        if parsed_quote_currencies:
            base_query = base_query.where(
                func.lower(Asset.quote_currency).in_(parsed_quote_currencies)
            )
        if parsed_signals:
            base_query = base_query.where(func.lower(SignalHistory.signal).in_(parsed_signals))
        if parsed_symbol_query:
            base_query = base_query.where(func.lower(Asset.symbol).like(f"%{parsed_symbol_query}%"))
        if min_score is not None:
            base_query = base_query.where(score_value >= min_score)
        if max_score is not None:
            base_query = base_query.where(score_value <= max_score)
        if min_confidence is not None:
            base_query = base_query.where(SignalHistory.confidence >= min_confidence)
        if blocked_by_risk is not None:
            base_query = base_query.where(SignalHistory.blocked_by_risk.is_(blocked_by_risk))

        total = session.scalar(
            select(func.count()).select_from(base_query.order_by(None).subquery())
        )
        ordered_query = base_query.order_by(
            _sort_expression(sort_by, sort_dir, score_value, SignalHistory, Asset),
            Asset.symbol.asc(),
        )
        rows = session.execute(ordered_query.limit(limit).offset(offset)).all()

    items = [_serialize_row(row) for row in rows]
    return {
        "status": "ok",
        "model_version": parsed_model_version,
        "filters": {
            "asset_types": sorted(parsed_asset_types),
            "exchanges": sorted(parsed_exchanges),
            "quote_currencies": sorted(parsed_quote_currencies),
            "signals": sorted(parsed_signals),
            "symbol_query": parsed_symbol_query or None,
            "min_score": min_score,
            "max_score": max_score,
            "min_confidence": min_confidence,
            "blocked_by_risk": blocked_by_risk,
            "sort_by": _SORT_FIELDS[sort_by],
            "sort_dir": sort_dir,
        },
        "pagination": {
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
            "returned": len(items),
        },
        "items": items,
    }


def _parse_csv_filter(value: str | None) -> set[str]:
    if value is None:
        return set()
    return {token.strip().lower() for token in value.split(",") if token.strip()}


def _sort_expression(
    sort_by: str,
    sort_dir: str,
    score_value,
    signal_model,
    asset_model,
):
    expression = {
        "score": score_value,
        "confidence": signal_model.confidence,
        "symbol": asset_model.symbol,
        "as_of_ts": signal_model.as_of_ts,
        "signal": signal_model.signal,
    }[sort_by]
    if sort_dir == "asc":
        return expression.asc()
    return expression.desc()


def _serialize_row(row) -> dict[str, object]:
    asset: Asset = row[0]
    signal: SignalHistory = row[1]
    score: ScoreHistory | None = row[2]
    score_value = _to_float(row[3])

    as_of_ts = normalize_to_utc(signal.as_of_ts).isoformat()
    return {
        "symbol": asset.symbol,
        "asset_type": asset.asset_type,
        "exchange": asset.exchange,
        "quote_currency": asset.quote_currency,
        "as_of_ts": as_of_ts,
        "signal": signal.signal,
        "score": score_value,
        "confidence": _to_float(signal.confidence),
        "blocked_by_risk": bool(signal.blocked_by_risk),
        "reasons": signal.reasons or [],
        "components": {
            "technical_score": None if score is None else _to_float(score.technical_score),
            "fundamental_score": None if score is None else _to_float(score.fundamental_score),
            "sentiment_risk_score": (
                None if score is None else _to_float(score.sentiment_risk_score)
            ),
        },
    }


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
