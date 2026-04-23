"""Tests for MA/RSI/MACD/ATR/Bollinger indicator calculations."""

from __future__ import annotations
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_screener.core.indicators import (
    ClosePricePoint,
    calculate_atr_bollinger_bands,
    calculate_latest_atr_bollinger_bands,
    calculate_latest_macd_signal,
    calculate_latest_ma50_ma200_rsi14,
    calculate_macd_signal,
    calculate_ma50_ma200_rsi14,
)


class FakeTAEngine:
    def __init__(self) -> None:
        self.sma_calls: list[int] = []
        self.rsi_calls: list[int] = []
        self.macd_calls: list[tuple[int, int, int]] = []
        self.macd_signal_calls: list[tuple[int, int, int]] = []
        self.atr_calls: list[int] = []
        self.bollinger_hband_calls: list[tuple[int, float]] = []
        self.bollinger_lband_calls: list[tuple[int, float]] = []
        self.atr_inputs: list[tuple[list[float], list[float], list[float]]] = []

    def sma(self, close_prices: list[float], *, window: int) -> list[float | None]:
        self.sma_calls.append(window)
        if window == 50:
            return [None, 100.5, 101.5]
        if window == 200:
            return [None, None, None]
        raise AssertionError(f"unexpected_window: {window}")

    def rsi(self, close_prices: list[float], *, window: int = 14) -> list[float | None]:
        self.rsi_calls.append(window)
        return [None, 49.0, 52.0]

    def macd(
        self,
        close_prices: list[float],
        *,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> list[float | None]:
        self.macd_calls.append((window_slow, window_fast, window_sign))
        return [None, 0.4, 0.8]

    def macd_signal(
        self,
        close_prices: list[float],
        *,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> list[float | None]:
        self.macd_signal_calls.append((window_slow, window_fast, window_sign))
        return [None, 0.3, 0.6]

    def atr(
        self,
        high_prices: list[float],
        low_prices: list[float],
        close_prices: list[float],
        *,
        window: int = 14,
    ) -> list[float | None]:
        self.atr_calls.append(window)
        self.atr_inputs.append((high_prices, low_prices, close_prices))
        return [None, 1.1, 1.2]

    def bollinger_hband(
        self,
        close_prices: list[float],
        *,
        window: int = 20,
        window_dev: float = 2.0,
    ) -> list[float | None]:
        self.bollinger_hband_calls.append((window, window_dev))
        return [None, 103.0, 104.0]

    def bollinger_lband(
        self,
        close_prices: list[float],
        *,
        window: int = 20,
        window_dev: float = 2.0,
    ) -> list[float | None]:
        self.bollinger_lband_calls.append((window, window_dev))
        return [None, 97.0, 98.0]


def test_calculate_ma50_ma200_rsi14_sorts_and_aligns_series() -> None:
    engine = FakeTAEngine()
    points = [
        ClosePricePoint(
            ts=datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
            close=Decimal("102"),
            high=Decimal("103"),
            low=Decimal("101"),
        ),
        ClosePricePoint(
            ts=datetime(2026, 4, 21, 0, 0),
            close=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
        ),
        ClosePricePoint(ts=datetime(2026, 4, 22, 0, 0, tzinfo=UTC), close=Decimal("101")),
    ]

    snapshots = calculate_ma50_ma200_rsi14(points, ta_engine=engine)

    assert engine.sma_calls == [50, 200]
    assert engine.rsi_calls == [14]
    assert engine.macd_calls == [(26, 12, 9)]
    assert engine.macd_signal_calls == [(26, 12, 9)]
    assert engine.atr_calls == [14]
    assert engine.bollinger_hband_calls == [(20, 2.0)]
    assert engine.bollinger_lband_calls == [(20, 2.0)]
    assert engine.atr_inputs == [
        ([101.0, 101.0, 103.0], [99.0, 101.0, 101.0], [100.0, 101.0, 102.0])
    ]
    assert [snapshot.ts for snapshot in snapshots] == [
        datetime(2026, 4, 21, 0, 0, tzinfo=UTC),
        datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
        datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
    ]
    assert snapshots[0].close == 100.0
    assert snapshots[1].ma50 == 100.5
    assert snapshots[2].ma50 == 101.5
    assert snapshots[2].ma200 is None
    assert snapshots[2].rsi14 == 52.0
    assert snapshots[2].macd == 0.8
    assert snapshots[2].macd_signal == 0.6
    assert snapshots[2].atr14 == 1.2
    assert snapshots[2].bb_upper == 104.0
    assert snapshots[2].bb_lower == 98.0


def test_calculate_latest_ma50_ma200_rsi14_returns_none_for_empty() -> None:
    assert calculate_latest_ma50_ma200_rsi14([]) is None


def test_calculate_latest_ma50_ma200_rsi14_returns_last_snapshot() -> None:
    engine = FakeTAEngine()
    points = [
        ClosePricePoint(ts=datetime(2026, 4, 21, tzinfo=UTC), close=100),
        ClosePricePoint(ts=datetime(2026, 4, 22, tzinfo=UTC), close=101),
        ClosePricePoint(ts=datetime(2026, 4, 23, tzinfo=UTC), close=102),
    ]

    latest = calculate_latest_ma50_ma200_rsi14(points, ta_engine=engine)

    assert latest is not None
    assert latest.ts == datetime(2026, 4, 23, tzinfo=UTC)
    assert latest.close == 102.0
    assert latest.ma50 == 101.5
    assert latest.rsi14 == 52.0
    assert latest.macd == 0.8
    assert latest.macd_signal == 0.6
    assert latest.atr14 == 1.2
    assert latest.bb_upper == 104.0
    assert latest.bb_lower == 98.0


def test_calculate_macd_signal_returns_macd_snapshots() -> None:
    engine = FakeTAEngine()
    points = [
        ClosePricePoint(ts=datetime(2026, 4, 21, tzinfo=UTC), close=100),
        ClosePricePoint(ts=datetime(2026, 4, 22, tzinfo=UTC), close=101),
        ClosePricePoint(ts=datetime(2026, 4, 23, tzinfo=UTC), close=102),
    ]

    snapshots = calculate_macd_signal(points, ta_engine=engine)

    assert [snapshot.ts for snapshot in snapshots] == [
        datetime(2026, 4, 21, tzinfo=UTC),
        datetime(2026, 4, 22, tzinfo=UTC),
        datetime(2026, 4, 23, tzinfo=UTC),
    ]
    assert snapshots[0].macd is None
    assert snapshots[1].macd == 0.4
    assert snapshots[2].macd_signal == 0.6


def test_calculate_latest_macd_signal_returns_none_for_empty() -> None:
    assert calculate_latest_macd_signal([]) is None


def test_calculate_latest_macd_signal_returns_last_snapshot() -> None:
    engine = FakeTAEngine()
    points = [
        ClosePricePoint(ts=datetime(2026, 4, 21, tzinfo=UTC), close=100),
        ClosePricePoint(ts=datetime(2026, 4, 22, tzinfo=UTC), close=101),
        ClosePricePoint(ts=datetime(2026, 4, 23, tzinfo=UTC), close=102),
    ]

    latest = calculate_latest_macd_signal(points, ta_engine=engine)

    assert latest is not None
    assert latest.ts == datetime(2026, 4, 23, tzinfo=UTC)
    assert latest.close == 102.0
    assert latest.macd == 0.8
    assert latest.macd_signal == 0.6


def test_calculate_atr_bollinger_bands_returns_snapshots() -> None:
    engine = FakeTAEngine()
    points = [
        ClosePricePoint(ts=datetime(2026, 4, 21, tzinfo=UTC), close=100),
        ClosePricePoint(ts=datetime(2026, 4, 22, tzinfo=UTC), close=101),
        ClosePricePoint(ts=datetime(2026, 4, 23, tzinfo=UTC), close=102),
    ]

    snapshots = calculate_atr_bollinger_bands(points, ta_engine=engine)

    assert [snapshot.ts for snapshot in snapshots] == [
        datetime(2026, 4, 21, tzinfo=UTC),
        datetime(2026, 4, 22, tzinfo=UTC),
        datetime(2026, 4, 23, tzinfo=UTC),
    ]
    assert snapshots[0].atr14 is None
    assert snapshots[1].bb_upper == 103.0
    assert snapshots[2].bb_lower == 98.0


def test_calculate_latest_atr_bollinger_bands_returns_none_for_empty() -> None:
    assert calculate_latest_atr_bollinger_bands([]) is None


def test_calculate_latest_atr_bollinger_bands_returns_last_snapshot() -> None:
    engine = FakeTAEngine()
    points = [
        ClosePricePoint(ts=datetime(2026, 4, 21, tzinfo=UTC), close=100),
        ClosePricePoint(ts=datetime(2026, 4, 22, tzinfo=UTC), close=101),
        ClosePricePoint(ts=datetime(2026, 4, 23, tzinfo=UTC), close=102),
    ]

    latest = calculate_latest_atr_bollinger_bands(points, ta_engine=engine)

    assert latest is not None
    assert latest.ts == datetime(2026, 4, 23, tzinfo=UTC)
    assert latest.close == 102.0
    assert latest.atr14 == 1.2
    assert latest.bb_upper == 104.0
    assert latest.bb_lower == 98.0


def test_calculate_ma50_ma200_rsi14_rejects_non_finite_close() -> None:
    engine = FakeTAEngine()

    with pytest.raises(ValueError, match="close_price_must_be_finite"):
        calculate_ma50_ma200_rsi14(
            [ClosePricePoint(ts=datetime(2026, 4, 21), close=float("nan"))],
            ta_engine=engine,
        )

    with pytest.raises(ValueError, match="close_price_must_be_finite"):
        calculate_ma50_ma200_rsi14(
            [ClosePricePoint(ts=datetime(2026, 4, 21), close=float("inf"))],
            ta_engine=engine,
        )


def test_calculate_ma50_ma200_rsi14_rejects_non_finite_high_low() -> None:
    engine = FakeTAEngine()

    with pytest.raises(ValueError, match="close_price_must_be_finite"):
        calculate_ma50_ma200_rsi14(
            [ClosePricePoint(ts=datetime(2026, 4, 21), close=100, high=float("nan"), low=99)],
            ta_engine=engine,
        )

    with pytest.raises(ValueError, match="close_price_must_be_finite"):
        calculate_ma50_ma200_rsi14(
            [ClosePricePoint(ts=datetime(2026, 4, 21), close=100, high=101, low=float("inf"))],
            ta_engine=engine,
        )


def test_calculate_ma50_ma200_rsi14_checks_series_lengths() -> None:
    class BadEngine(FakeTAEngine):
        def rsi(self, close_prices: list[float], *, window: int = 14) -> list[float | None]:
            return [50.0]  # intentionally wrong length

    with pytest.raises(ValueError, match="indicator_series_length_mismatch"):
        calculate_ma50_ma200_rsi14(
            [
                ClosePricePoint(ts=datetime(2026, 4, 21), close=100),
                ClosePricePoint(ts=datetime(2026, 4, 22), close=101),
                ClosePricePoint(ts=datetime(2026, 4, 23), close=102),
            ],
            ta_engine=BadEngine(),
        )
