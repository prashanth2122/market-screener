"""Tests for symbol metadata ingestion job."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset
from market_screener.jobs.symbol_metadata import (
    SymbolMetadataIngestionJob,
    SymbolUniverseParseError,
    load_symbol_universe,
)


def test_load_symbol_universe_validates_shape(tmp_path: Path) -> None:
    universe_path = tmp_path / "symbols.json"
    universe_path.write_text(json.dumps({"symbols": [{"symbol": "AAPL"}]}), encoding="utf-8")

    with pytest.raises(SymbolUniverseParseError):
        load_symbol_universe(universe_path)


def test_symbol_metadata_job_inserts_and_updates_assets(tmp_path: Path) -> None:
    universe_path = tmp_path / "symbols.json"
    universe_path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "AAPL",
                        "asset_type": "equity",
                        "exchange": "US",
                        "quote_currency": "USD",
                    },
                    {
                        "symbol": "BTC",
                        "asset_type": "crypto",
                        "exchange": "GLOBAL",
                        "quote_currency": "USD",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    job = SymbolMetadataIngestionJob(session_local, universe_path)
    first = job.run()

    assert first.processed == 2
    assert first.created == 2
    assert first.updated == 0
    assert first.unchanged == 0

    universe_path.write_text(
        json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "AAPL",
                        "asset_type": "equity",
                        "exchange": "NASDAQ",
                        "quote_currency": "USD",
                    },
                    {
                        "symbol": "BTC",
                        "asset_type": "crypto",
                        "exchange": "GLOBAL",
                        "quote_currency": "USD",
                    },
                    {
                        "symbol": "ETH",
                        "asset_type": "crypto",
                        "exchange": "GLOBAL",
                        "quote_currency": "USD",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    second = job.run()

    assert second.processed == 3
    assert second.created == 1
    assert second.updated == 1
    assert second.unchanged == 1

    third = job.run()
    assert third.processed == 3
    assert third.created == 0
    assert third.updated == 0
    assert third.unchanged == 3

    with session_local() as session:
        stored_symbols = sorted(session.scalars(select(Asset.symbol)).all())
        aapl = session.scalar(select(Asset).where(Asset.symbol == "AAPL"))

    assert stored_symbols == ["AAPL", "BTC", "ETH"]
    assert aapl is not None
    assert aapl.exchange == "NASDAQ"
