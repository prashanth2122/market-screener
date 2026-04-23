"""Technical-analysis library integration helpers."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("market_screener.core.ta_library")


@dataclass(frozen=True)
class TALibraryStatus:
    """Availability details for the TA integration backend."""

    backend: str
    available: bool
    version: str | None
    error: str | None = None


@dataclass(frozen=True)
class _TAModules:
    pandas: Any
    trend: Any
    momentum: Any
    volatility: Any
    version: str | None


class TALibraryNotAvailableError(RuntimeError):
    """Raised when TA computations are requested without TA library support."""


def _default_ta_loader() -> tuple[_TAModules | None, str | None]:
    try:
        pandas_module = importlib.import_module("pandas")
        trend_module = importlib.import_module("ta.trend")
        momentum_module = importlib.import_module("ta.momentum")
        volatility_module = importlib.import_module("ta.volatility")
    except Exception as exc:
        return None, f"ta_library_unavailable: {exc}"

    version: str | None
    try:
        version = importlib.metadata.version("ta")
    except importlib.metadata.PackageNotFoundError:
        version = None

    return (
        _TAModules(
            pandas=pandas_module,
            trend=trend_module,
            momentum=momentum_module,
            volatility=volatility_module,
            version=version,
        ),
        None,
    )


def get_ta_library_status(
    loader: Any = _default_ta_loader,
) -> TALibraryStatus:
    """Return TA backend availability status."""

    modules, load_error = loader()
    if modules is None:
        return TALibraryStatus(
            backend="ta",
            available=False,
            version=None,
            error=load_error or "ta_library_unavailable",
        )

    return TALibraryStatus(
        backend="ta",
        available=True,
        version=modules.version,
        error=None,
    )


class TALibraryEngine:
    """Thin wrapper around the `ta` indicator library."""

    def __init__(
        self,
        modules: _TAModules | None,
        *,
        load_error: str | None = None,
    ) -> None:
        self._modules = modules
        self._load_error = load_error

    @classmethod
    def from_loader(cls, loader: Any = _default_ta_loader) -> "TALibraryEngine":
        """Create engine from a loader function."""

        modules, load_error = loader()
        return cls(modules, load_error=load_error)

    @property
    def status(self) -> TALibraryStatus:
        """Return current backend availability."""

        if self._modules is None:
            return TALibraryStatus(
                backend="ta",
                available=False,
                version=None,
                error=self._load_error or "ta_library_unavailable",
            )
        return TALibraryStatus(
            backend="ta",
            available=True,
            version=self._modules.version,
            error=None,
        )

    def sma(self, close_prices: list[float], *, window: int) -> list[float | None]:
        """Compute simple moving average over close prices."""

        self._validate_window(window)
        series = self._to_series(close_prices)
        indicator = self._require_modules().trend.SMAIndicator(
            close=series,
            window=window,
            fillna=False,
        )
        return _series_to_optional_floats(indicator.sma_indicator().tolist())

    def ema(self, close_prices: list[float], *, window: int) -> list[float | None]:
        """Compute exponential moving average over close prices."""

        self._validate_window(window)
        series = self._to_series(close_prices)
        indicator = self._require_modules().trend.EMAIndicator(
            close=series,
            window=window,
            fillna=False,
        )
        return _series_to_optional_floats(indicator.ema_indicator().tolist())

    def rsi(self, close_prices: list[float], *, window: int = 14) -> list[float | None]:
        """Compute RSI over close prices."""

        self._validate_window(window)
        series = self._to_series(close_prices)
        indicator = self._require_modules().momentum.RSIIndicator(
            close=series,
            window=window,
            fillna=False,
        )
        return _series_to_optional_floats(indicator.rsi().tolist())

    def macd(
        self,
        close_prices: list[float],
        *,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> list[float | None]:
        """Compute MACD over close prices."""

        self._validate_macd_windows(
            window_slow=window_slow,
            window_fast=window_fast,
            window_sign=window_sign,
        )
        series = self._to_series(close_prices)
        indicator = self._require_modules().trend.MACD(
            close=series,
            window_slow=window_slow,
            window_fast=window_fast,
            window_sign=window_sign,
            fillna=False,
        )
        return _series_to_optional_floats(indicator.macd().tolist())

    def macd_signal(
        self,
        close_prices: list[float],
        *,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> list[float | None]:
        """Compute MACD signal line over close prices."""

        self._validate_macd_windows(
            window_slow=window_slow,
            window_fast=window_fast,
            window_sign=window_sign,
        )
        series = self._to_series(close_prices)
        indicator = self._require_modules().trend.MACD(
            close=series,
            window_slow=window_slow,
            window_fast=window_fast,
            window_sign=window_sign,
            fillna=False,
        )
        return _series_to_optional_floats(indicator.macd_signal().tolist())

    def atr(
        self,
        high_prices: list[float],
        low_prices: list[float],
        close_prices: list[float],
        *,
        window: int = 14,
    ) -> list[float | None]:
        """Compute ATR over high/low/close prices."""

        self._validate_window(window)
        high_series, low_series, close_series = self._to_hlc_series(
            high_prices=high_prices,
            low_prices=low_prices,
            close_prices=close_prices,
        )
        indicator = self._require_modules().volatility.AverageTrueRange(
            high=high_series,
            low=low_series,
            close=close_series,
            window=window,
            fillna=False,
        )
        return _series_to_optional_floats(indicator.average_true_range().tolist())

    def bollinger_hband(
        self,
        close_prices: list[float],
        *,
        window: int = 20,
        window_dev: float = 2.0,
    ) -> list[float | None]:
        """Compute Bollinger upper band over close prices."""

        self._validate_window(window)
        self._validate_positive(value=window_dev, error_code="window_dev_must_be_positive")
        series = self._to_series(close_prices)
        indicator = self._require_modules().volatility.BollingerBands(
            close=series,
            window=window,
            window_dev=window_dev,
            fillna=False,
        )
        return _series_to_optional_floats(indicator.bollinger_hband().tolist())

    def bollinger_lband(
        self,
        close_prices: list[float],
        *,
        window: int = 20,
        window_dev: float = 2.0,
    ) -> list[float | None]:
        """Compute Bollinger lower band over close prices."""

        self._validate_window(window)
        self._validate_positive(value=window_dev, error_code="window_dev_must_be_positive")
        series = self._to_series(close_prices)
        indicator = self._require_modules().volatility.BollingerBands(
            close=series,
            window=window,
            window_dev=window_dev,
            fillna=False,
        )
        return _series_to_optional_floats(indicator.bollinger_lband().tolist())

    def _to_series(self, close_prices: list[float]) -> Any:
        if not close_prices:
            raise ValueError("close_prices_must_not_be_empty")
        return self._require_modules().pandas.Series(close_prices, dtype="float64")

    def _to_hlc_series(
        self,
        *,
        high_prices: list[float],
        low_prices: list[float],
        close_prices: list[float],
    ) -> tuple[Any, Any, Any]:
        self._validate_matching_series_lengths(
            high_prices=high_prices,
            low_prices=low_prices,
            close_prices=close_prices,
        )
        return (
            self._to_series(high_prices),
            self._to_series(low_prices),
            self._to_series(close_prices),
        )

    def _require_modules(self) -> _TAModules:
        if self._modules is None:
            message = self._load_error or "ta_library_unavailable"
            raise TALibraryNotAvailableError(
                f"{message}. Install dependencies from backend/pyproject.toml."
            )
        return self._modules

    @staticmethod
    def _validate_window(window: int) -> None:
        if window < 1:
            raise ValueError("window_must_be_positive")

    @classmethod
    def _validate_macd_windows(
        cls,
        *,
        window_slow: int,
        window_fast: int,
        window_sign: int,
    ) -> None:
        cls._validate_window(window_slow)
        cls._validate_window(window_fast)
        cls._validate_window(window_sign)

    @staticmethod
    def _validate_matching_series_lengths(
        *,
        high_prices: list[float],
        low_prices: list[float],
        close_prices: list[float],
    ) -> None:
        if not (len(high_prices) == len(low_prices) == len(close_prices)):
            raise ValueError("price_series_length_mismatch")

    @staticmethod
    def _validate_positive(*, value: float, error_code: str) -> None:
        if value <= 0:
            raise ValueError(error_code)


def _series_to_optional_floats(values: list[Any]) -> list[float | None]:
    normalized: list[float | None] = []
    for value in values:
        if value is None:
            normalized.append(None)
            continue
        converted = float(value)
        if math.isnan(converted):
            normalized.append(None)
        else:
            normalized.append(converted)
    return normalized


def main() -> None:
    """CLI entrypoint for TA backend availability check."""

    status = get_ta_library_status()
    logger.info(
        "ta_library_status",
        extra={
            "backend": status.backend,
            "available": status.available,
            "version": status.version,
            "error": status.error,
        },
    )
    print(
        "ta_library_status:"
        f" backend={status.backend}"
        f" available={status.available}"
        f" version={status.version or 'none'}"
        f" error={status.error or 'none'}"
    )


if __name__ == "__main__":
    main()
