"""Tests for TA library integration helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from market_screener.core.ta_library import (
    TALibraryEngine,
    TALibraryNotAvailableError,
    get_ta_library_status,
)


class _FakeSeries:
    def __init__(self, values: list[float], *, dtype: str = "float64") -> None:
        self.values = values
        self.dtype = dtype


class _FakeSeriesResult:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return self._values


class _FakeSMAIndicator:
    def __init__(self, *, close: _FakeSeries, window: int, fillna: bool) -> None:
        self._close = close
        self._window = window

    def sma_indicator(self) -> _FakeSeriesResult:
        output: list[float] = []
        for index in range(len(self._close.values)):
            if index + 1 < self._window:
                output.append(float("nan"))
                continue
            window_values = self._close.values[index + 1 - self._window : index + 1]
            output.append(sum(window_values) / self._window)
        return _FakeSeriesResult(output)


class _FakeEMAIndicator:
    def __init__(self, *, close: _FakeSeries, window: int, fillna: bool) -> None:
        self._close = close
        self._window = window

    def ema_indicator(self) -> _FakeSeriesResult:
        if not self._close.values:
            return _FakeSeriesResult([])
        alpha = 2 / (self._window + 1)
        output: list[float] = [self._close.values[0]]
        for value in self._close.values[1:]:
            output.append((value * alpha) + (output[-1] * (1 - alpha)))
        return _FakeSeriesResult(output)


class _FakeRSIIndicator:
    def __init__(self, *, close: _FakeSeries, window: int, fillna: bool) -> None:
        self._close = close

    def rsi(self) -> _FakeSeriesResult:
        output: list[float] = [float("nan")]
        output.extend([50.0] * (len(self._close.values) - 1))
        return _FakeSeriesResult(output)


class _FakeMACDIndicator:
    def __init__(
        self,
        *,
        close: _FakeSeries,
        window_slow: int,
        window_fast: int,
        window_sign: int,
        fillna: bool,
    ) -> None:
        self._close = close
        self._window_fast = window_fast
        self._window_sign = window_sign

    def macd(self) -> _FakeSeriesResult:
        output: list[float] = []
        for index, value in enumerate(self._close.values):
            if index + 1 < self._window_fast:
                output.append(float("nan"))
                continue
            output.append(value - self._close.values[index - 1])
        return _FakeSeriesResult(output)

    def macd_signal(self) -> _FakeSeriesResult:
        output: list[float] = []
        for index, value in enumerate(self._close.values):
            if index + 1 < self._window_sign:
                output.append(float("nan"))
                continue
            output.append(value - self._close.values[index - 2])
        return _FakeSeriesResult(output)


class _FakeATRIndicator:
    def __init__(
        self,
        *,
        high: _FakeSeries,
        low: _FakeSeries,
        close: _FakeSeries,
        window: int,
        fillna: bool,
    ) -> None:
        self._high = high
        self._low = low
        self._window = window

    def average_true_range(self) -> _FakeSeriesResult:
        output: list[float] = []
        for index in range(len(self._high.values)):
            if index + 1 < self._window:
                output.append(float("nan"))
                continue
            output.append(self._high.values[index] - self._low.values[index])
        return _FakeSeriesResult(output)


class _FakeBollingerBands:
    def __init__(
        self,
        *,
        close: _FakeSeries,
        window: int,
        window_dev: float,
        fillna: bool,
    ) -> None:
        self._close = close
        self._window = window
        self._window_dev = window_dev

    def bollinger_hband(self) -> _FakeSeriesResult:
        output: list[float] = []
        for index, value in enumerate(self._close.values):
            if index + 1 < self._window:
                output.append(float("nan"))
                continue
            output.append(value + self._window_dev)
        return _FakeSeriesResult(output)

    def bollinger_lband(self) -> _FakeSeriesResult:
        output: list[float] = []
        for index, value in enumerate(self._close.values):
            if index + 1 < self._window:
                output.append(float("nan"))
                continue
            output.append(value - self._window_dev)
        return _FakeSeriesResult(output)


class _FakePandasModule:
    Series = _FakeSeries


class _FakeTrendModule:
    SMAIndicator = _FakeSMAIndicator
    EMAIndicator = _FakeEMAIndicator
    MACD = _FakeMACDIndicator


class _FakeMomentumModule:
    RSIIndicator = _FakeRSIIndicator


class _FakeVolatilityModule:
    AverageTrueRange = _FakeATRIndicator
    BollingerBands = _FakeBollingerBands


@dataclass(frozen=True)
class _FakeModules:
    pandas: object
    trend: object
    momentum: object
    volatility: object
    version: str | None


def test_ta_library_status_reports_unavailable_loader_failure() -> None:
    status = get_ta_library_status(loader=lambda: (None, "ta_library_unavailable: missing"))

    assert status.available is False
    assert status.backend == "ta"
    assert status.version is None
    assert "missing" in (status.error or "")


def test_ta_library_engine_raises_when_library_unavailable() -> None:
    engine = TALibraryEngine.from_loader(loader=lambda: (None, "ta_library_unavailable"))

    with pytest.raises(TALibraryNotAvailableError):
        engine.sma([100.0, 101.0], window=2)


def test_ta_library_engine_uses_loaded_modules() -> None:
    modules = _FakeModules(
        pandas=_FakePandasModule(),
        trend=_FakeTrendModule(),
        momentum=_FakeMomentumModule(),
        volatility=_FakeVolatilityModule(),
        version="0.11.0",
    )
    engine = TALibraryEngine.from_loader(loader=lambda: (modules, None))

    sma = engine.sma([100.0, 101.0, 102.0], window=2)
    ema = engine.ema([100.0, 101.0, 102.0], window=2)
    rsi = engine.rsi([100.0, 101.0, 102.0], window=2)
    macd = engine.macd([100.0, 101.0, 102.0], window_fast=2, window_sign=2)
    macd_signal = engine.macd_signal([100.0, 101.0, 102.0], window_fast=2, window_sign=3)
    atr = engine.atr([101.0, 102.0, 103.0], [99.0, 100.0, 101.0], [100.0, 101.0, 102.0], window=2)
    bb_upper = engine.bollinger_hband([100.0, 101.0, 102.0], window=2, window_dev=2.0)
    bb_lower = engine.bollinger_lband([100.0, 101.0, 102.0], window=2, window_dev=2.0)

    assert sma[0] is None
    assert sma[1:] == [100.5, 101.5]
    assert ema[0] == 100.0
    assert math.isclose(ema[1], 100.66666666666667)
    assert rsi[0] is None
    assert rsi[1:] == [50.0, 50.0]
    assert macd[0] is None
    assert macd[1:] == [1.0, 1.0]
    assert macd_signal[0] is None
    assert macd_signal[1] is None
    assert macd_signal[2] == 2.0
    assert atr[0] is None
    assert atr[1:] == [2.0, 2.0]
    assert bb_upper[0] is None
    assert bb_upper[1:] == [103.0, 104.0]
    assert bb_lower[0] is None
    assert bb_lower[1:] == [99.0, 100.0]


def test_ta_library_engine_atr_rejects_mismatched_series_lengths() -> None:
    modules = _FakeModules(
        pandas=_FakePandasModule(),
        trend=_FakeTrendModule(),
        momentum=_FakeMomentumModule(),
        volatility=_FakeVolatilityModule(),
        version="0.11.0",
    )
    engine = TALibraryEngine.from_loader(loader=lambda: (modules, None))

    with pytest.raises(ValueError, match="price_series_length_mismatch"):
        engine.atr([101.0], [99.0, 100.0], [100.0, 101.0], window=2)
