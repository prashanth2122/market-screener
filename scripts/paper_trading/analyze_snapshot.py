from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Item:
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
    parser = argparse.ArgumentParser(
        description="Analyze screener snapshot JSON into a review markdown."
    )
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    payload = json.loads(args.json_file.read_text(encoding="utf-8"))
    items_raw = payload.get("items", [])
    items = [_parse_item(item) for item in items_raw if isinstance(item, dict)]

    md = _render_markdown(items, top=max(1, int(args.top)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    return 0


def _parse_item(item: dict[str, Any]) -> Item:
    return Item(
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


def _render_markdown(items: list[Item], *, top: int) -> str:
    signal_counts = Counter((item.signal or "unknown") for item in items)
    type_counts = Counter((item.asset_type or "unknown") for item in items)
    risk_blocked = sum(1 for item in items if item.blocked_by_risk)

    scored = [item for item in items if item.score is not None]
    scored.sort(key=lambda i: (i.score is None, -(i.score or 0.0), i.symbol))

    lines: list[str] = []
    lines.append("## Snapshot Summary")
    lines.append("")
    lines.append(f"- items: {len(items)}")
    lines.append(f"- blocked_by_risk: {risk_blocked}")
    if type_counts:
        lines.append(
            "- by_asset_type: " + ", ".join(f"{k}={v}" for k, v in type_counts.most_common())
        )
    if signal_counts:
        lines.append(
            "- by_signal: " + ", ".join(f"{k}={v}" for k, v in signal_counts.most_common())
        )
    lines.append("")

    lines.append(f"## Top {top} (By Score)")
    lines.append("")
    lines.append("| # | Symbol | Type | Exch | Signal | Score | Conf | Risk |")
    lines.append("|---:|---|---|---|---|---:|---:|---|")
    for idx, item in enumerate(scored[:top], start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    item.symbol,
                    item.asset_type,
                    item.exchange,
                    item.signal,
                    "" if item.score is None else f"{item.score:.2f}",
                    "" if item.confidence is None else f"{item.confidence:.2f}",
                    "blocked" if item.blocked_by_risk else "ok",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
