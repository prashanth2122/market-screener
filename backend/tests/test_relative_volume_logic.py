"""Tests for relative volume calculation logic."""

from __future__ import annotations

from datetime import UTC, datetime

from market_screener.core.relative_volume import (
    RelativeVolumeInput,
    calculate_relative_volume,
    calculate_relative_volume_series,
)


def _point(
    *,
    day: int,
    current_volume: float | None,
    baseline_volumes: list[float],
) -> RelativeVolumeInput:
    return RelativeVolumeInput(
        ts=datetime(2026, 4, day, tzinfo=UTC),
        current_volume=current_volume,
        baseline_volumes=baseline_volumes,
    )


def test_calculate_relative_volume_spike() -> None:
    decision = calculate_relative_volume(
        _point(day=21, current_volume=1500.0, baseline_volumes=[900.0, 1000.0, 1100.0]),
        spike_threshold=1.4,
        dry_up_threshold=0.7,
    )

    assert decision.state == "spike"
    assert decision.ratio is not None and decision.ratio >= 1.4


def test_calculate_relative_volume_dry_up() -> None:
    decision = calculate_relative_volume(
        _point(day=21, current_volume=400.0, baseline_volumes=[900.0, 1000.0, 1100.0]),
        spike_threshold=1.5,
        dry_up_threshold=0.5,
    )

    assert decision.state == "dry_up"
    assert decision.ratio is not None and decision.ratio <= 0.5


def test_calculate_relative_volume_normal() -> None:
    decision = calculate_relative_volume(
        _point(day=21, current_volume=950.0, baseline_volumes=[900.0, 1000.0, 1100.0]),
        spike_threshold=1.5,
        dry_up_threshold=0.7,
    )

    assert decision.state == "normal"
    assert decision.ratio is not None


def test_calculate_relative_volume_unknown_when_current_missing() -> None:
    decision = calculate_relative_volume(
        _point(day=21, current_volume=None, baseline_volumes=[900.0, 1000.0]),
    )

    assert decision.state == "unknown"
    assert decision.reasons == ["missing_current_volume"]


def test_calculate_relative_volume_unknown_when_baseline_missing() -> None:
    decision = calculate_relative_volume(
        _point(day=21, current_volume=1000.0, baseline_volumes=[]),
    )

    assert decision.state == "unknown"
    assert decision.reasons == ["missing_baseline_volume"]


def test_calculate_relative_volume_series_sorts_by_timestamp() -> None:
    points = [
        _point(day=23, current_volume=1500.0, baseline_volumes=[900.0, 1000.0, 1100.0]),
        _point(day=21, current_volume=950.0, baseline_volumes=[900.0, 1000.0, 1100.0]),
        _point(day=22, current_volume=400.0, baseline_volumes=[900.0, 1000.0, 1100.0]),
    ]

    decisions = calculate_relative_volume_series(
        points,
        spike_threshold=1.4,
        dry_up_threshold=0.5,
    )

    assert [decision.ts.day for decision in decisions] == [21, 22, 23]
    assert [decision.state for decision in decisions] == ["normal", "dry_up", "spike"]
