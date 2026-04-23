"""EPS and revenue growth metrics computation for fundamentals scoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime


METRIC_ORDER = ("eps_growth", "revenue_growth")


@dataclass(frozen=True)
class GrowthMetricsFundamentals:
    """Fundamentals inputs needed for EPS/revenue growth computation."""

    period_end: date
    eps_basic: float | None
    eps_diluted: float | None
    revenue: float | None


@dataclass(frozen=True)
class GrowthMetricsResult:
    """Computed growth metrics for one period against its prior period."""

    period_end: date
    eps_basis: str
    eps_growth_ratio: float | None
    eps_growth_percent: float | None
    revenue_growth_ratio: float | None
    revenue_growth_percent: float | None
    unavailable_metrics: list[str]
    diagnostics: dict[str, float | None]


def compute_growth_metrics(
    current: GrowthMetricsFundamentals,
    previous: GrowthMetricsFundamentals,
) -> GrowthMetricsResult:
    """Compute EPS and revenue growth from current and previous period fundamentals."""

    current_eps, previous_eps, eps_basis = _resolve_eps_pair(current, previous)
    eps_growth_ratio = _safe_growth_ratio(current_eps, previous_eps)
    revenue_growth_ratio = _safe_growth_ratio(current.revenue, previous.revenue)

    unavailable_metrics = []
    if eps_growth_ratio is None:
        unavailable_metrics.append("eps_growth")
    if revenue_growth_ratio is None:
        unavailable_metrics.append("revenue_growth")

    diagnostics = {
        "current_eps_basic": current.eps_basic,
        "current_eps_diluted": current.eps_diluted,
        "previous_eps_basic": previous.eps_basic,
        "previous_eps_diluted": previous.eps_diluted,
        "current_eps_selected": current_eps,
        "previous_eps_selected": previous_eps,
        "current_revenue": current.revenue,
        "previous_revenue": previous.revenue,
    }

    return GrowthMetricsResult(
        period_end=current.period_end,
        eps_basis=eps_basis,
        eps_growth_ratio=eps_growth_ratio,
        eps_growth_percent=_ratio_to_percent(eps_growth_ratio),
        revenue_growth_ratio=revenue_growth_ratio,
        revenue_growth_percent=_ratio_to_percent(revenue_growth_ratio),
        unavailable_metrics=unavailable_metrics,
        diagnostics=diagnostics,
    )


def compute_growth_metrics_series(
    periods: list[GrowthMetricsFundamentals],
) -> list[GrowthMetricsResult]:
    """Compute growth metrics for each period using the prior period as baseline."""

    if len(periods) < 2:
        return []
    ordered = sorted(periods, key=lambda item: item.period_end)
    return [
        compute_growth_metrics(ordered[index], ordered[index - 1])
        for index in range(1, len(ordered))
    ]


def _resolve_eps_pair(
    current: GrowthMetricsFundamentals,
    previous: GrowthMetricsFundamentals,
) -> tuple[float | None, float | None, str]:
    if current.eps_diluted is not None and previous.eps_diluted is not None:
        return current.eps_diluted, previous.eps_diluted, "diluted"
    if current.eps_basic is not None and previous.eps_basic is not None:
        return current.eps_basic, previous.eps_basic, "basic"
    return None, None, "unavailable"


def _safe_growth_ratio(current_value: float | None, previous_value: float | None) -> float | None:
    if current_value is None or previous_value is None:
        return None
    if previous_value == 0:
        return None
    return (current_value - previous_value) / abs(previous_value)


def _ratio_to_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100.0


def main() -> None:
    """CLI entrypoint for EPS/revenue growth metrics smoke check."""

    previous = GrowthMetricsFundamentals(
        period_end=date(2024, 12, 31),
        eps_basic=2.30,
        eps_diluted=2.20,
        revenue=1200.0,
    )
    current = GrowthMetricsFundamentals(
        period_end=date(2025, 12, 31),
        eps_basic=2.80,
        eps_diluted=2.70,
        revenue=1440.0,
    )
    result = compute_growth_metrics(current, previous)
    now = datetime.now(UTC).isoformat()
    print(
        "growth_metrics:"
        f" ts={now}"
        f" period_end={result.period_end.isoformat()}"
        f" eps_basis={result.eps_basis}"
        f" eps_growth_pct={None if result.eps_growth_percent is None else round(result.eps_growth_percent, 2)}"
        f" revenue_growth_pct={None if result.revenue_growth_percent is None else round(result.revenue_growth_percent, 2)}"
        f" unavailable={len(result.unavailable_metrics)}"
    )


if __name__ == "__main__":
    main()
