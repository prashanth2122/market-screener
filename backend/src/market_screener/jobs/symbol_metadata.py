"""Symbol metadata ingestion job."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.db.models.core import Asset
from market_screener.db.session import SessionFactory, create_session_factory_from_settings

logger = logging.getLogger("market_screener.jobs.symbol_metadata")


class SymbolUniverseParseError(ValueError):
    """Raised when symbol universe file has invalid shape or data."""


@dataclass(frozen=True)
class SymbolRecord:
    """Normalized symbol metadata entry."""

    symbol: str
    asset_type: str
    exchange: str
    quote_currency: str
    base_currency: str | None = None
    active: bool = True


@dataclass(frozen=True)
class SymbolIngestionResult:
    """Outcome summary for a symbol metadata ingestion run."""

    processed: int
    created: int
    updated: int
    unchanged: int


def load_symbol_universe(path: Path) -> list[SymbolRecord]:
    """Load and validate symbol records from universe JSON file."""

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SymbolUniverseParseError(f"symbol_universe_file_missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SymbolUniverseParseError(f"symbol_universe_invalid_json: {path}") from exc

    if not isinstance(payload, dict):
        raise SymbolUniverseParseError("symbol_universe_payload_must_be_object")

    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise SymbolUniverseParseError("symbol_universe_symbols_must_be_array")

    records: list[SymbolRecord] = []
    for index, entry in enumerate(symbols):
        if not isinstance(entry, dict):
            raise SymbolUniverseParseError(f"symbol_entry_{index}_must_be_object")

        symbol = _require_non_empty_str(entry, "symbol", index).upper()
        asset_type = _require_non_empty_str(entry, "asset_type", index).lower()
        exchange = _require_non_empty_str(entry, "exchange", index).upper()
        quote_currency = _require_non_empty_str(entry, "quote_currency", index).upper()
        base_currency_raw = entry.get("base_currency")
        base_currency = base_currency_raw.upper() if isinstance(base_currency_raw, str) else None
        active = bool(entry.get("active", True))

        records.append(
            SymbolRecord(
                symbol=symbol,
                asset_type=asset_type,
                exchange=exchange,
                quote_currency=quote_currency,
                base_currency=base_currency,
                active=active,
            )
        )

    return records


class SymbolMetadataIngestionJob:
    """Upsert symbol universe metadata into `assets` table."""

    def __init__(self, session_factory: SessionFactory, universe_path: Path) -> None:
        self._session_factory = session_factory
        self._universe_path = universe_path

    def run(self) -> SymbolIngestionResult:
        records = load_symbol_universe(self._universe_path)
        symbols = [record.symbol for record in records]

        created = 0
        updated = 0
        unchanged = 0

        with self._session_factory() as session:
            existing_by_symbol = {
                asset.symbol: asset
                for asset in session.scalars(select(Asset).where(Asset.symbol.in_(symbols))).all()
            }

            for record in records:
                existing = existing_by_symbol.get(record.symbol)
                if existing is None:
                    session.add(
                        Asset(
                            symbol=record.symbol,
                            asset_type=record.asset_type,
                            exchange=record.exchange,
                            base_currency=record.base_currency,
                            quote_currency=record.quote_currency,
                            active=record.active,
                        )
                    )
                    created += 1
                    continue

                changed = False
                if existing.asset_type != record.asset_type:
                    existing.asset_type = record.asset_type
                    changed = True
                if existing.exchange != record.exchange:
                    existing.exchange = record.exchange
                    changed = True
                if existing.base_currency != record.base_currency:
                    existing.base_currency = record.base_currency
                    changed = True
                if existing.quote_currency != record.quote_currency:
                    existing.quote_currency = record.quote_currency
                    changed = True
                if existing.active != record.active:
                    existing.active = record.active
                    changed = True

                if changed:
                    updated += 1
                else:
                    unchanged += 1

            session.commit()

        return SymbolIngestionResult(
            processed=len(records),
            created=created,
            updated=updated,
            unchanged=unchanged,
        )


def run_symbol_metadata_ingestion(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    universe_path: Path | None = None,
) -> SymbolIngestionResult:
    """Run symbol metadata ingestion with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_path = universe_path or Path(resolved_settings.symbol_universe_file)
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    job = SymbolMetadataIngestionJob(resolved_session_factory, resolved_path)
    return job.run()


def _require_non_empty_str(entry: dict[str, Any], key: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SymbolUniverseParseError(f"symbol_entry_{index}_{key}_must_be_non_empty_string")
    return value.strip()


def main() -> None:
    """CLI entrypoint for manual symbol metadata ingestion runs."""

    result = run_symbol_metadata_ingestion()
    logger.info(
        "symbol_metadata_ingestion_completed",
        extra={
            "processed": result.processed,
            "created": result.created,
            "updated": result.updated,
            "unchanged": result.unchanged,
        },
    )
    print(
        "symbol_metadata_ingestion:"
        f" processed={result.processed}"
        f" created={result.created}"
        f" updated={result.updated}"
        f" unchanged={result.unchanged}"
    )


if __name__ == "__main__":
    main()
