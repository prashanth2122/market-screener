"""Shared price payload normalization and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from market_screener.core.timezone import normalize_to_utc, to_utc_unix_seconds
from market_screener.db.models.core import Price
from market_screener.db.session import SessionFactory


class PriceNormalizationError(ValueError):
    """Raised when provider payload cannot be normalized to the common schema."""


@dataclass(frozen=True)
class NormalizedPricePoint:
    """Common canonical OHLCV schema for all provider payloads."""

    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None


def normalize_finnhub_stock_candles(payload: dict[str, Any]) -> list[NormalizedPricePoint]:
    """Normalize Finnhub stock candle payload to common OHLCV schema."""

    status = payload.get("s")
    if status == "no_data":
        return []
    if status != "ok":
        raise PriceNormalizationError(f"finnhub_candles_invalid_status: {status}")

    timestamps = _as_list(payload.get("t"), "t")
    opens = _as_list(payload.get("o"), "o")
    highs = _as_list(payload.get("h"), "h")
    lows = _as_list(payload.get("l"), "l")
    closes = _as_list(payload.get("c"), "c")
    volumes_raw = _as_list(payload.get("v"), "v")

    lengths = {
        len(timestamps),
        len(opens),
        len(highs),
        len(lows),
        len(closes),
        len(volumes_raw),
    }
    if len(lengths) != 1:
        raise PriceNormalizationError("finnhub_candles_array_lengths_mismatch")

    points: list[NormalizedPricePoint] = []
    for ts_raw, open_raw, high_raw, low_raw, close_raw, volume_raw in zip(
        timestamps, opens, highs, lows, closes, volumes_raw, strict=True
    ):
        if not isinstance(ts_raw, (int, float)):
            raise PriceNormalizationError("finnhub_candles_timestamp_must_be_number")

        ts = datetime.fromtimestamp(int(ts_raw), tz=UTC)
        points.append(
            NormalizedPricePoint(
                ts=ts,
                open=_to_decimal(open_raw, "finnhub_candles_open"),
                high=_to_decimal(high_raw, "finnhub_candles_high"),
                low=_to_decimal(low_raw, "finnhub_candles_low"),
                close=_to_decimal(close_raw, "finnhub_candles_close"),
                volume=_to_decimal(volume_raw, "finnhub_candles_volume", allow_none=True),
            )
        )
    return points


def normalize_coingecko_ohlc(payload: list[Any]) -> list[NormalizedPricePoint]:
    """Normalize CoinGecko OHLC payload to common OHLCV schema."""

    points: list[NormalizedPricePoint] = []
    for index, row in enumerate(payload):
        if not isinstance(row, list) or len(row) < 5:
            raise PriceNormalizationError(f"coingecko_ohlc_row_{index}_must_be_array_len_5")

        ts_raw = row[0]
        if not isinstance(ts_raw, (int, float)):
            raise PriceNormalizationError(f"coingecko_ohlc_row_{index}_timestamp_must_be_number")

        ts = datetime.fromtimestamp(float(ts_raw) / 1000.0, tz=UTC)
        points.append(
            NormalizedPricePoint(
                ts=ts,
                open=_to_decimal(row[1], f"coingecko_ohlc_row_{index}_open"),
                high=_to_decimal(row[2], f"coingecko_ohlc_row_{index}_high"),
                low=_to_decimal(row[3], f"coingecko_ohlc_row_{index}_low"),
                close=_to_decimal(row[4], f"coingecko_ohlc_row_{index}_close"),
                volume=None,
            )
        )
    return points


def normalize_alpha_vantage_fx_daily(payload: dict[str, Any]) -> list[NormalizedPricePoint]:
    """Normalize Alpha Vantage FX_DAILY payload to common OHLCV schema."""

    series = _find_dict_key_with_prefix(payload, "Time Series FX")
    if series is None:
        raise PriceNormalizationError("alpha_vantage_fx_daily_series_missing")

    points: list[NormalizedPricePoint] = []
    for ts_label, row in series.items():
        if not isinstance(ts_label, str):
            raise PriceNormalizationError("alpha_vantage_fx_daily_ts_must_be_string")
        if not isinstance(row, dict):
            raise PriceNormalizationError("alpha_vantage_fx_daily_row_must_be_object")

        ts = _parse_date_to_utc(ts_label)
        points.append(
            NormalizedPricePoint(
                ts=ts,
                open=_to_decimal(row.get("1. open"), "alpha_vantage_fx_open"),
                high=_to_decimal(row.get("2. high"), "alpha_vantage_fx_high"),
                low=_to_decimal(row.get("3. low"), "alpha_vantage_fx_low"),
                close=_to_decimal(row.get("4. close"), "alpha_vantage_fx_close"),
                volume=None,
            )
        )
    points.sort(key=lambda point: point.ts)
    return points


def normalize_alpha_vantage_commodity_daily(payload: dict[str, Any]) -> list[NormalizedPricePoint]:
    """Normalize Alpha Vantage commodity payload to common OHLCV schema."""

    data = payload.get("data")
    if not isinstance(data, list):
        raise PriceNormalizationError("alpha_vantage_commodity_data_must_be_array")

    points: list[NormalizedPricePoint] = []
    for index, row in enumerate(data):
        if not isinstance(row, dict):
            raise PriceNormalizationError(f"alpha_vantage_commodity_row_{index}_must_be_object")

        date_raw = row.get("date")
        value_raw = row.get("value")
        if not isinstance(date_raw, str):
            raise PriceNormalizationError(
                f"alpha_vantage_commodity_row_{index}_date_must_be_string"
            )

        value = _to_decimal(value_raw, f"alpha_vantage_commodity_row_{index}_value")
        ts = _parse_date_to_utc(date_raw)
        points.append(
            NormalizedPricePoint(
                ts=ts,
                open=value,
                high=value,
                low=value,
                close=value,
                volume=None,
            )
        )
    points.sort(key=lambda point: point.ts)
    return points


def persist_normalized_prices(
    session_factory: SessionFactory,
    *,
    asset_id: int,
    source: str,
    ingest_id: str,
    points: list[NormalizedPricePoint],
) -> tuple[int, int]:
    """Persist normalized OHLCV points for one asset, skipping duplicate timestamps."""

    with session_factory() as session:
        existing_ts = {
            to_utc_unix_seconds(ts)
            for ts in session.scalars(
                select(Price.ts).where(
                    Price.asset_id == asset_id,
                    Price.source == source,
                )
            ).all()
        }

        ingested_rows = 0
        skipped_rows = 0
        for point in points:
            normalized_ts = normalize_to_utc(point.ts)
            point_ts = to_utc_unix_seconds(normalized_ts)
            if point_ts in existing_ts:
                skipped_rows += 1
                continue

            session.add(
                Price(
                    asset_id=asset_id,
                    ts=normalized_ts,
                    open=point.open,
                    high=point.high,
                    low=point.low,
                    close=point.close,
                    volume=point.volume,
                    source=source,
                    ingest_id=ingest_id,
                )
            )
            ingested_rows += 1
            existing_ts.add(point_ts)

        session.commit()

    return ingested_rows, skipped_rows


def _as_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise PriceNormalizationError(f"{field_name}_must_be_array")
    return value


def _to_decimal(value: Any, field_name: str, *, allow_none: bool = False) -> Decimal | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, (int, float, str)):
        raise PriceNormalizationError(f"{field_name}_must_be_numeric")
    return Decimal(str(value))


def _parse_date_to_utc(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise PriceNormalizationError(f"date_must_match_yyyy_mm_dd: {value}") from exc
    return parsed.replace(tzinfo=UTC)


def _find_dict_key_with_prefix(payload: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    for key, value in payload.items():
        if isinstance(key, str) and key.startswith(prefix) and isinstance(value, dict):
            return value
    return None
