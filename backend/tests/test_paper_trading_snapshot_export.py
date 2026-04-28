"""Tests for paper-trading screener snapshot export tooling."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_snapshot_screener_converts_json_to_csv_and_md(tmp_path: Path) -> None:
    payload = {
        "status": "ok",
        "items": [
            {
                "symbol": "AAPL",
                "asset_type": "equity",
                "exchange": "US",
                "quote_currency": "USD",
                "as_of_ts": "2026-04-28T00:00:00Z",
                "signal": "buy",
                "score": 75.12,
                "confidence": 0.71,
                "blocked_by_risk": False,
            }
        ],
    }
    json_file = tmp_path / "screener.json"
    csv_file = tmp_path / "screener.csv"
    md_file = tmp_path / "screener.md"
    json_file.write_text(json.dumps(payload), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "paper_trading" / "snapshot_screener.py"

    subprocess.run(
        ["python", str(script), str(json_file), "--csv", str(csv_file), "--md", str(md_file)],
        cwd=str(repo_root),
        check=True,
    )

    assert csv_file.exists()
    assert md_file.exists()
    assert "AAPL" in csv_file.read_text(encoding="utf-8")
    assert "| AAPL |" in md_file.read_text(encoding="utf-8")
