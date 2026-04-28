"""Guards to ensure model version bumps are documented."""

from __future__ import annotations

from pathlib import Path

from market_screener.core.score_factors import SCORE_MODEL_VERSION


def test_score_model_version_has_changelog_entry() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    changelog = repo_root / "docs" / "MODEL_CHANGELOG.md"
    assert changelog.exists()

    text = changelog.read_text(encoding="utf-8")
    assert f"## {SCORE_MODEL_VERSION} " in text or f"## {SCORE_MODEL_VERSION}\n" in text
