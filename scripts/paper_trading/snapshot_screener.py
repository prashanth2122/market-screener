from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Row:
    symbol: str
    asset_type: str
    exchange: str
    quote_currency: str
    as_of_ts: str
    signal: str
    score: float | None
    confidence: float | None
    blocked_by_risk: bool


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert screener JSON payload to CSV/Markdown.")
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--md", type=Path, default=None)
    args = parser.parse_args()

    payload = json.loads(args.json_file.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    rows = [_parse_row(item) for item in items if isinstance(item, dict)]

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        _write_csv(args.csv, rows)
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(_to_markdown(rows), encoding="utf-8")

    return 0


def _parse_row(item: dict[str, Any]) -> Row:
    return Row(
        symbol=str(item.get("symbol") or ""),
        asset_type=str(item.get("asset_type") or ""),
        exchange=str(item.get("exchange") or ""),
        quote_currency=str(item.get("quote_currency") or ""),
        as_of_ts=str(item.get("as_of_ts") or ""),
        signal=str(item.get("signal") or ""),
        score=_to_float(item.get("score")),
        confidence=_to_float(item.get("confidence")),
        blocked_by_risk=bool(item.get("blocked_by_risk") or False),
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_csv(path: Path, rows: list[Row]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "symbol",
                "asset_type",
                "exchange",
                "quote_currency",
                "as_of_ts",
                "signal",
                "score",
                "confidence",
                "blocked_by_risk",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.symbol,
                    row.asset_type,
                    row.exchange,
                    row.quote_currency,
                    row.as_of_ts,
                    row.signal,
                    "" if row.score is None else f"{row.score:.4f}",
                    "" if row.confidence is None else f"{row.confidence:.4f}",
                    "true" if row.blocked_by_risk else "false",
                ]
            )


def _to_markdown(rows: list[Row]) -> str:
    lines: list[str] = []
    lines.append("| # | Symbol | Type | Exch | Quote | Signal | Score | Conf | Risk |")
    lines.append("|---:|---|---|---|---|---|---:|---:|---|")
    for idx, row in enumerate(rows, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    row.symbol,
                    row.asset_type,
                    row.exchange,
                    row.quote_currency,
                    row.signal,
                    "" if row.score is None else f"{row.score:.2f}",
                    "" if row.confidence is None else f"{row.confidence:.2f}",
                    "blocked" if row.blocked_by_risk else "ok",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
