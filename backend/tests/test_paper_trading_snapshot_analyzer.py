"""Tests for paper-trading snapshot analyzer."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_analyze_snapshot_writes_markdown(tmp_path: Path) -> None:
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
            },
            {
                "symbol": "BTC",
                "asset_type": "crypto",
                "exchange": "GLOBAL",
                "quote_currency": "USD",
                "as_of_ts": "2026-04-28T00:00:00Z",
                "signal": "strong_buy",
                "score": 88.0,
                "confidence": 0.82,
                "blocked_by_risk": True,
            },
        ],
    }
    json_file = tmp_path / "screener.json"
    out_file = tmp_path / "review.md"
    json_file.write_text(json.dumps(payload), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "paper_trading" / "analyze_snapshot.py"

    subprocess.run(
        ["python", str(script), str(json_file), "--out", str(out_file), "--top", "1"],
        cwd=str(repo_root),
        check=True,
    )

    text = out_file.read_text(encoding="utf-8")
    assert "Snapshot Summary" in text
    assert "blocked_by_risk: 1" in text
    assert "Top 1" in text
    assert "| 1 | BTC |" in text
