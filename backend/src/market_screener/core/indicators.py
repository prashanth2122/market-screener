"""Core indicator calculations for MA, RSI, MACD, ATR, and Bollinger Bands."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from market_screener.core.ta_library import TALibraryEngine
from market_screener.core.timezone import normalize_to_utc

logger = logging.getLogger("market_screener.core.indicators")


class TAEngine(Protocol):
    """Minimal TA engine contract needed for indicator calculations."""

    def sma(self, close_prices: list[float], *, window: int) -> list[float | None]:
        """Return SMA values aligned to close series."""

    def rsi(self, close_prices: list[float], *, window: int = 14) -> list[float | None]:
        """Return RSI values aligned to close series."""

    def macd(
        self,
        close_prices: list[float],
        *,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> list[float | None]:
        """Return MACD values aligned to close series."""

    def macd_signal(
        self,
        close_prices: list[float],
        *,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> list[float | None]:
        """Return MACD signal line values aligned to close series."""

    def atr(
        self,
        high_prices: list[float],
        low_prices: list[float],
        close_prices: list[float],
        *,
        window: int = 14,
    ) -> list[float | None]:
        """Return ATR values aligned to OHLC series."""

    def bollinger_hband(
        self,
        close_prices: list[float],
        *,
        window: int = 20,
        window_dev: float = 2.0,
    ) -> list[float | None]:
        """Return Bollinger upper-band values aligned to close series."""

    def bollinger_lband(
        self,
        close_prices: list[float],
        *,
        window: int = 20,
        window_dev: float = 2.0,
    ) -> list[float | None]:
        """Return Bollinger lower-band values aligned to close series."""


@dataclass(frozen=True)
class ClosePricePoint:
    """Input close-price point for indicator calculations."""

    ts: datetime
    close: Decimal | float | int
    high: Decimal | float | int | None = None
    low: Decimal | float | int | None = None


@dataclass(frozen=True)
class IndicatorSnapshot:
    """Calculated indicator values for one timestamp."""

    ts: datetime
    close: float
    ma50: float | None
    ma200: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    atr14: float | None
    bb_upper: float | None
    bb_lower: float | None


@dataclass(frozen=True)
class MACDSignalSnapshot:
    """Calculated MACD and signal values for one timestamp."""

    ts: datetime
    close: float
    macd: float | None
    macd_signal: float | None


@dataclass(frozen=True)
class ATRBollingerSnapshot:
    """Calculated ATR and Bollinger values for one timestamp."""

    ts: datetime
    close: float
    atr14: float | None
    bb_upper: float | None
    bb_lower: float | None


def calculate_ma50_ma200_rsi14(
    points: list[ClosePricePoint],
    *,
    ta_engine: TAEngine | None = None,
) -> list[IndicatorSnapshot]:
    """Compute MA50, MA200, RSI14, MACD, ATR14, and BB series for price points."""

    if not points:
        return []

    engine = ta_engine or TALibraryEngine.from_loader()
    normalized_points = sorted(
        (
            ClosePricePoint(
                ts=normalize_to_utc(point.ts),
                close=point.close,
                high=point.high,
                low=point.low,
            )
            for point in points
        ),
        key=lambda point: point.ts,
    )
    close_prices = [_to_finite_float(point.close) for point in normalized_points]
    high_prices = [
        _to_finite_float(point.high if point.high is not None else point.close)
        for point in normalized_points
    ]
    low_prices = [
        _to_finite_float(point.low if point.low is not None else point.close)
        for point in normalized_points
    ]
    ma50 = engine.sma(close_prices, window=50)
    ma200 = engine.sma(close_prices, window=200)
    rsi14 = engine.rsi(close_prices, window=14)
    macd = engine.macd(close_prices)
    macd_signal = engine.macd_signal(close_prices)
    atr14 = engine.atr(high_prices, low_prices, close_prices, window=14)
    bb_upper = engine.bollinger_hband(close_prices, window=20, window_dev=2.0)
    bb_lower = engine.bollinger_lband(close_prices, window=20, window_dev=2.0)
    if not (
        len(ma50)
        == len(ma200)
        == len(rsi14)
        == len(macd)
        == len(macd_signal)
        == len(atr14)
        == len(bb_upper)
        == len(bb_lower)
        == len(normalized_points)
    ):
        raise ValueError("indicator_series_length_mismatch")

    return [
        IndicatorSnapshot(
            ts=point.ts,
            close=close_prices[index],
            ma50=ma50[index],
            ma200=ma200[index],
            rsi14=rsi14[index],
            macd=macd[index],
            macd_signal=macd_signal[index],
            atr14=atr14[index],
            bb_upper=bb_upper[index],
            bb_lower=bb_lower[index],
        )
        for index, point in enumerate(normalized_points)
    ]


def calculate_latest_ma50_ma200_rsi14(
    points: list[ClosePricePoint],
    *,
    ta_engine: TAEngine | None = None,
) -> IndicatorSnapshot | None:
    """Compute the latest combined indicator snapshot."""

    series = calculate_ma50_ma200_rsi14(points, ta_engine=ta_engine)
    return series[-1] if series else None


def calculate_macd_signal(
    points: list[ClosePricePoint],
    *,
    ta_engine: TAEngine | None = None,
) -> list[MACDSignalSnapshot]:
    """Compute MACD and signal series for close-price points."""

    snapshots = calculate_ma50_ma200_rsi14(points, ta_engine=ta_engine)
    return [
        MACDSignalSnapshot(
            ts=snapshot.ts,
            close=snapshot.close,
            macd=snapshot.macd,
            macd_signal=snapshot.macd_signal,
        )
        for snapshot in snapshots
    ]


def calculate_latest_macd_signal(
    points: list[ClosePricePoint],
    *,
    ta_engine: TAEngine | None = None,
) -> MACDSignalSnapshot | None:
    """Compute the latest MACD and signal snapshot."""

    series = calculate_macd_signal(points, ta_engine=ta_engine)
    return series[-1] if series else None


def calculate_atr_bollinger_bands(
    points: list[ClosePricePoint],
    *,
    ta_engine: TAEngine | None = None,
) -> list[ATRBollingerSnapshot]:
    """Compute ATR14 and Bollinger bands series for price points."""

    snapshots = calculate_ma50_ma200_rsi14(points, ta_engine=ta_engine)
    return [
        ATRBollingerSnapshot(
            ts=snapshot.ts,
            close=snapshot.close,
            atr14=snapshot.atr14,
            bb_upper=snapshot.bb_upper,
            bb_lower=snapshot.bb_lower,
        )
        for snapshot in snapshots
    ]


def calculate_latest_atr_bollinger_bands(
    points: list[ClosePricePoint],
    *,
    ta_engine: TAEngine | None = None,
) -> ATRBollingerSnapshot | None:
    """Compute the latest ATR14/Bollinger snapshot."""

    series = calculate_atr_bollinger_bands(points, ta_engine=ta_engine)
    return series[-1] if series else None


def _to_finite_float(value: Decimal | float | int) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError("close_price_must_be_finite")
    return converted


def main() -> None:
    """CLI entrypoint for indicator calculation smoke check."""

    sample_points = [
        ClosePricePoint(ts=datetime(2026, 4, day + 1), close=100 + day) for day in range(210)
    ]
    latest = calculate_latest_ma50_ma200_rsi14(sample_points)
    logger.info(
        "indicator_calculation_completed",
        extra={
            "input_points": len(sample_points),
            "has_latest": latest is not None,
        },
    )
    if latest is None:
        print("indicator_calculation: has_latest=False")
        return
    print(
        "indicator_calculation:"
        f" ts={latest.ts.isoformat()}"
        f" close={latest.close}"
        f" ma50={latest.ma50}"
        f" ma200={latest.ma200}"
        f" rsi14={latest.rsi14}"
        f" macd={latest.macd}"
        f" macd_signal={latest.macd_signal}"
        f" atr14={latest.atr14}"
        f" bb_upper={latest.bb_upper}"
        f" bb_lower={latest.bb_lower}"
    )


if __name__ == "__main__":
    main()
