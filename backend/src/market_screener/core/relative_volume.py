"""Relative volume calculation logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RelativeVolumeInput:
    """Input feature set for relative volume calculation."""

    ts: datetime
    current_volume: float | None
    baseline_volumes: list[float]


@dataclass(frozen=True)
class RelativeVolumeDecision:
    """Relative volume decision for one timestamp."""

    ts: datetime
    ratio: float | None
    state: str
    current_volume: float | None
    baseline_avg_volume: float | None
    reasons: list[str]


VALID_RVOL_STATES = {"spike", "normal", "dry_up", "unknown"}


def calculate_relative_volume(
    point: RelativeVolumeInput,
    *,
    spike_threshold: float = 1.5,
    dry_up_threshold: float = 0.7,
) -> RelativeVolumeDecision:
    """Calculate relative volume ratio and classify its state."""

    clean_baseline = [value for value in point.baseline_volumes if value > 0]
    if point.current_volume is None:
        return RelativeVolumeDecision(
            ts=point.ts,
            ratio=None,
            state="unknown",
            current_volume=None,
            baseline_avg_volume=None,
            reasons=["missing_current_volume"],
        )
    if point.current_volume < 0:
        return RelativeVolumeDecision(
            ts=point.ts,
            ratio=None,
            state="unknown",
            current_volume=point.current_volume,
            baseline_avg_volume=None,
            reasons=["invalid_current_volume"],
        )
    if not clean_baseline:
        return RelativeVolumeDecision(
            ts=point.ts,
            ratio=None,
            state="unknown",
            current_volume=point.current_volume,
            baseline_avg_volume=None,
            reasons=["missing_baseline_volume"],
        )

    baseline_avg = sum(clean_baseline) / len(clean_baseline)
    if baseline_avg <= 0:
        return RelativeVolumeDecision(
            ts=point.ts,
            ratio=None,
            state="unknown",
            current_volume=point.current_volume,
            baseline_avg_volume=baseline_avg,
            reasons=["invalid_baseline_average"],
        )

    ratio = point.current_volume / baseline_avg
    spike_cutoff = max(1.0, spike_threshold)
    dry_up_cutoff = min(1.0, max(0.0, dry_up_threshold))

    if ratio >= spike_cutoff:
        return RelativeVolumeDecision(
            ts=point.ts,
            ratio=ratio,
            state="spike",
            current_volume=point.current_volume,
            baseline_avg_volume=baseline_avg,
            reasons=["relative_volume_above_spike_threshold"],
        )
    if ratio <= dry_up_cutoff:
        return RelativeVolumeDecision(
            ts=point.ts,
            ratio=ratio,
            state="dry_up",
            current_volume=point.current_volume,
            baseline_avg_volume=baseline_avg,
            reasons=["relative_volume_below_dry_up_threshold"],
        )
    return RelativeVolumeDecision(
        ts=point.ts,
        ratio=ratio,
        state="normal",
        current_volume=point.current_volume,
        baseline_avg_volume=baseline_avg,
        reasons=["relative_volume_within_normal_band"],
    )


def calculate_relative_volume_series(
    points: list[RelativeVolumeInput],
    *,
    spike_threshold: float = 1.5,
    dry_up_threshold: float = 0.7,
) -> list[RelativeVolumeDecision]:
    """Calculate relative volume across a timestamp-ordered series."""

    return [
        calculate_relative_volume(
            point,
            spike_threshold=spike_threshold,
            dry_up_threshold=dry_up_threshold,
        )
        for point in sorted(points, key=lambda item: item.ts)
    ]
