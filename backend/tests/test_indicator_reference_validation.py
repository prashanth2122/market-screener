"""Tests for indicator reference checkpoint validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_screener.core.indicator_reference_validation import (
    DEFAULT_REFERENCE_FILE,
    validate_indicator_reference_values,
)
from market_screener.core.ta_library import get_ta_library_status

pytestmark = pytest.mark.skipif(
    not get_ta_library_status().available,
    reason="TA backend unavailable",
)


def test_indicator_reference_validation_passes_with_default_reference() -> None:
    result = validate_indicator_reference_values()

    assert result.reference_file == DEFAULT_REFERENCE_FILE
    assert result.passed is True
    assert result.checkpoint_count >= 1
    assert result.checked_fields >= result.checkpoint_count
    assert result.mismatches == []


def test_indicator_reference_validation_detects_checkpoint_mismatch(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_REFERENCE_FILE.read_text(encoding="utf-8"))
    payload["expected_checkpoints"][0]["ma50"] = payload["expected_checkpoints"][0]["ma50"] + 10.0

    reference_file = tmp_path / "indicator_reference_bad.json"
    reference_file.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_indicator_reference_values(reference_file=reference_file)

    assert result.passed is False
    assert any(
        mismatch.checkpoint_index == payload["expected_checkpoints"][0]["index"]
        and mismatch.field == "ma50"
        for mismatch in result.mismatches
    )


def test_indicator_reference_validation_rejects_mismatched_dataset_lengths(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_REFERENCE_FILE.read_text(encoding="utf-8"))
    payload["dataset"]["low"] = payload["dataset"]["low"][:-1]

    reference_file = tmp_path / "indicator_reference_bad_lengths.json"
    reference_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="reference_dataset_length_mismatch"):
        validate_indicator_reference_values(reference_file=reference_file)
