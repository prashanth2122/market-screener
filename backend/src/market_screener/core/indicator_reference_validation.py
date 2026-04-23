"""Reference-value validation for indicator outputs."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from market_screener.core.indicators import (
    ClosePricePoint,
    IndicatorSnapshot,
    calculate_ma50_ma200_rsi14,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REFERENCE_FILE = _REPO_ROOT / "config" / "indicator_reference_values_v1.json"
INDICATOR_FIELDS = (
    "close",
    "ma50",
    "ma200",
    "rsi14",
    "macd",
    "macd_signal",
    "atr14",
    "bb_upper",
    "bb_lower",
)


@dataclass(frozen=True)
class IndicatorReferenceMismatch:
    """Single mismatch found while validating reference checkpoints."""

    checkpoint_index: int
    field: str
    expected: float | str | None
    actual: float | str | None


@dataclass(frozen=True)
class IndicatorReferenceValidationResult:
    """Aggregated result for indicator reference validation."""

    reference_file: Path
    case_name: str
    tolerance: float
    checkpoint_count: int
    checked_fields: int
    mismatches: list[IndicatorReferenceMismatch]

    @property
    def passed(self) -> bool:
        """Return True when all checkpoints match expected values."""

        return not self.mismatches


def validate_indicator_reference_values(
    *,
    reference_file: Path | None = None,
) -> IndicatorReferenceValidationResult:
    """Validate indicator outputs against frozen reference checkpoints."""

    resolved_reference_file = reference_file or DEFAULT_REFERENCE_FILE
    payload = _load_reference_payload(resolved_reference_file)
    tolerance = float(payload.get("tolerance", 1e-6))
    points = _build_points_from_reference(payload)
    snapshots = calculate_ma50_ma200_rsi14(points)

    mismatches: list[IndicatorReferenceMismatch] = []
    expected_checkpoints = payload["expected_checkpoints"]
    checked_fields = 0

    for checkpoint in expected_checkpoints:
        index = int(checkpoint["index"])
        if index < 0 or index >= len(snapshots):
            raise ValueError("reference_checkpoint_out_of_range")
        snapshot = snapshots[index]
        actual = _snapshot_to_mapping(snapshot)

        checked_fields += 1
        expected_ts = str(checkpoint["ts"])
        if expected_ts != actual["ts"]:
            mismatches.append(
                IndicatorReferenceMismatch(
                    checkpoint_index=index,
                    field="ts",
                    expected=expected_ts,
                    actual=actual["ts"],
                )
            )

        for field in INDICATOR_FIELDS:
            checked_fields += 1
            expected_value = checkpoint.get(field)
            actual_value = actual[field]
            if _values_equal(expected_value, actual_value, tolerance=tolerance):
                continue
            mismatches.append(
                IndicatorReferenceMismatch(
                    checkpoint_index=index,
                    field=field,
                    expected=expected_value,
                    actual=actual_value,
                )
            )

    return IndicatorReferenceValidationResult(
        reference_file=resolved_reference_file,
        case_name=str(payload["dataset"]["name"]),
        tolerance=tolerance,
        checkpoint_count=len(expected_checkpoints),
        checked_fields=checked_fields,
        mismatches=mismatches,
    )


def _load_reference_payload(reference_file: Path) -> dict[str, Any]:
    if not reference_file.exists():
        raise FileNotFoundError(f"reference_file_not_found: {reference_file}")
    payload = json.loads(reference_file.read_text(encoding="utf-8"))
    required_top_level = {"dataset", "expected_checkpoints"}
    if not required_top_level.issubset(payload):
        raise ValueError("invalid_reference_payload")
    dataset = payload["dataset"]
    required_dataset_fields = {"name", "start_ts", "interval_days", "close", "high", "low"}
    if not required_dataset_fields.issubset(dataset):
        raise ValueError("invalid_reference_dataset")
    return payload


def _build_points_from_reference(payload: dict[str, Any]) -> list[ClosePricePoint]:
    dataset = payload["dataset"]
    start_ts = datetime.fromisoformat(str(dataset["start_ts"]))
    interval_days = int(dataset["interval_days"])
    close_values = [float(value) for value in dataset["close"]]
    high_values = [float(value) for value in dataset["high"]]
    low_values = [float(value) for value in dataset["low"]]

    if interval_days < 1:
        raise ValueError("reference_interval_days_must_be_positive")
    if not close_values:
        raise ValueError("reference_dataset_must_not_be_empty")
    if not (len(close_values) == len(high_values) == len(low_values)):
        raise ValueError("reference_dataset_length_mismatch")

    return [
        ClosePricePoint(
            ts=start_ts + timedelta(days=index * interval_days),
            close=close_values[index],
            high=high_values[index],
            low=low_values[index],
        )
        for index in range(len(close_values))
    ]


def _snapshot_to_mapping(snapshot: IndicatorSnapshot) -> dict[str, float | str | None]:
    return {
        "ts": snapshot.ts.isoformat(),
        "close": snapshot.close,
        "ma50": snapshot.ma50,
        "ma200": snapshot.ma200,
        "rsi14": snapshot.rsi14,
        "macd": snapshot.macd,
        "macd_signal": snapshot.macd_signal,
        "atr14": snapshot.atr14,
        "bb_upper": snapshot.bb_upper,
        "bb_lower": snapshot.bb_lower,
    }


def _values_equal(expected: Any, actual: Any, *, tolerance: float) -> bool:
    if expected is None or actual is None:
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(expected), float(actual), rel_tol=0.0, abs_tol=tolerance)
    return expected == actual


def main() -> None:
    """CLI entrypoint for indicator reference validation."""

    parser = argparse.ArgumentParser(
        description="Validate indicator outputs against frozen reference values."
    )
    parser.add_argument(
        "--reference-file",
        type=Path,
        default=DEFAULT_REFERENCE_FILE,
        help="Path to reference JSON file.",
    )
    args = parser.parse_args()
    result = validate_indicator_reference_values(reference_file=args.reference_file)

    print(
        "indicator_reference_validation:"
        f" case={result.case_name}"
        f" checkpoints={result.checkpoint_count}"
        f" checked_fields={result.checked_fields}"
        f" mismatches={len(result.mismatches)}"
        f" passed={result.passed}"
    )
    for mismatch in result.mismatches:
        print(
            "indicator_reference_mismatch:"
            f" index={mismatch.checkpoint_index}"
            f" field={mismatch.field}"
            f" expected={mismatch.expected}"
            f" actual={mismatch.actual}"
        )
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
