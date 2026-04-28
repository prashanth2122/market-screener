"""Provider adapter interfaces and implementations for ingestion jobs."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import date
from typing import ContextManager, Protocol

from market_screener.db.models.core import Asset
from market_screener.jobs.price_normalization import (
    NormalizedPricePoint,
    PriceNormalizationError,
    normalize_alpha_vantage_commodity_daily,
    normalize_alpha_vantage_fx_daily,
    normalize_coingecko_ohlc,
    normalize_finnhub_stock_candles,
)
from market_screener.providers.alpha_vantage import AlphaVantageClient
from market_screener.providers.coingecko import CoinGeckoClient
from market_screener.providers.finnhub import FinnhubClient


class AdapterNormalizationError(ValueError):
    """Raised when adapter cannot normalize provider payload.

    The raw provider payload is attached so ingestion jobs can route the event to a
    dead-letter queue rather than retrying endlessly.
    """

    def __init__(self, message: str, *, payload: object | None) -> None:
        super().__init__(message)
        self.payload = payload


class AdapterSymbolMappingError(LookupError):
    """Raised when adapter cannot map one symbol to provider identifiers."""


class EquityIngestionAdapter(Protocol):
    """Adapter contract for equity OHLCV fetch + normalization."""

    def fetch_candles(
        self,
        symbol: str,
        *,
        resolution: str,
        from_unix: int,
        to_unix: int,
    ) -> list[NormalizedPricePoint]:
        """Fetch and normalize equity candles for one symbol."""


class CryptoIngestionAdapter(Protocol):
    """Adapter contract for crypto OHLCV fetch + normalization."""

    def fetch_candles(
        self,
        symbol: str,
        *,
        vs_currency: str,
        days: int,
    ) -> list[NormalizedPricePoint]:
        """Fetch and normalize crypto candles for one symbol."""


class MacroIngestionAdapter(Protocol):
    """Adapter contract for macro OHLCV fetch + normalization."""

    def fetch_candles(
        self,
        asset: Asset,
        *,
        forex_outputsize: str,
        commodity_interval: str,
        window_start_date: date,
    ) -> list[NormalizedPricePoint] | None:
        """Fetch and normalize macro candles for one asset."""


EquityAdapterFactory = Callable[[], ContextManager[EquityIngestionAdapter]]
CryptoAdapterFactoryBuilder = Callable[
    [dict[str, str]],
    ContextManager[CryptoIngestionAdapter],
]
MacroAdapterFactory = Callable[[], ContextManager[MacroIngestionAdapter]]


class FinnhubEquityAdapter:
    """Finnhub-backed implementation of the equity ingestion adapter."""

    def __init__(self, client: FinnhubClient) -> None:
        self._client = client

    def fetch_candles(
        self,
        symbol: str,
        *,
        resolution: str,
        from_unix: int,
        to_unix: int,
    ) -> list[NormalizedPricePoint]:
        payload = self._client.get_stock_candles(
            symbol,
            resolution=resolution,
            from_unix=from_unix,
            to_unix=to_unix,
        )
        try:
            return normalize_finnhub_stock_candles(payload)
        except PriceNormalizationError as exc:
            raise AdapterNormalizationError(str(exc), payload=payload) from exc


class CoinGeckoCryptoAdapter:
    """CoinGecko-backed implementation of the crypto ingestion adapter."""

    def __init__(self, client: CoinGeckoClient, symbol_to_coin_id: dict[str, str]) -> None:
        self._client = client
        self._symbol_to_coin_id = {
            symbol.upper(): coin_id for symbol, coin_id in symbol_to_coin_id.items()
        }

    def fetch_candles(
        self,
        symbol: str,
        *,
        vs_currency: str,
        days: int,
    ) -> list[NormalizedPricePoint]:
        coin_id = self._symbol_to_coin_id.get(symbol.upper())
        if not coin_id:
            raise AdapterSymbolMappingError(f"symbol_mapping_missing: {symbol.upper()}")

        payload = self._client.get_coin_ohlc(
            coin_id,
            vs_currency=vs_currency,
            days=days,
        )
        try:
            return normalize_coingecko_ohlc(payload)
        except PriceNormalizationError as exc:
            raise AdapterNormalizationError(str(exc), payload=payload) from exc


class AlphaVantageMacroAdapter:
    """Alpha Vantage-backed implementation of the macro ingestion adapter."""

    def __init__(self, client: AlphaVantageClient) -> None:
        self._client = client

    def fetch_candles(
        self,
        asset: Asset,
        *,
        forex_outputsize: str,
        commodity_interval: str,
        window_start_date: date,
    ) -> list[NormalizedPricePoint] | None:
        payload: object | None = None
        try:
            if asset.asset_type == "forex":
                if not asset.base_currency:
                    return None
                payload = self._client.get_fx_daily(
                    asset.base_currency,
                    asset.quote_currency,
                    outputsize=forex_outputsize,
                )
                points = normalize_alpha_vantage_fx_daily(payload)
                return [point for point in points if point.ts.date() >= window_start_date]

            if asset.asset_type == "commodity":
                payload = self._client.fetch(
                    asset.symbol.upper(),
                    {"interval": commodity_interval},
                )
                points = normalize_alpha_vantage_commodity_daily(payload)
                return [point for point in points if point.ts.date() >= window_start_date]
        except PriceNormalizationError as exc:
            raise AdapterNormalizationError(str(exc), payload=payload) from exc

        return None


def build_finnhub_equity_adapter_factory(
    client_factory: Callable[[], FinnhubClient],
) -> EquityAdapterFactory:
    """Build contextmanager factory for Finnhub equity adapter."""

    @contextmanager
    def _factory() -> Generator[EquityIngestionAdapter, None, None]:
        with client_factory() as client:
            yield FinnhubEquityAdapter(client)

    return _factory


def build_coingecko_crypto_adapter_factory(
    client_factory: Callable[[], CoinGeckoClient],
) -> CryptoAdapterFactoryBuilder:
    """Build contextmanager factory builder for CoinGecko crypto adapter."""

    @contextmanager
    def _factory(
        symbol_to_coin_id: dict[str, str]
    ) -> Generator[CryptoIngestionAdapter, None, None]:
        with client_factory() as client:
            yield CoinGeckoCryptoAdapter(client, symbol_to_coin_id)

    return _factory


def build_alpha_vantage_macro_adapter_factory(
    client_factory: Callable[[], AlphaVantageClient],
) -> MacroAdapterFactory:
    """Build contextmanager factory for Alpha Vantage macro adapter."""

    @contextmanager
    def _factory() -> Generator[MacroIngestionAdapter, None, None]:
        with client_factory() as client:
            yield AlphaVantageMacroAdapter(client)

    return _factory
