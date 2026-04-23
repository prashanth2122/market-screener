"""Tests for EPS and revenue growth metrics computation logic."""

from __future__ import annotations

from datetime import date

from market_screener.core.growth_metrics import (
    GrowthMetricsFundamentals,
    compute_growth_metrics,
    compute_growth_metrics_series,
)


def _period(
    *,
    period_end: date,
    eps_basic: float | None,
    eps_diluted: float | None,
    revenue: float | None,
) -> GrowthMetricsFundamentals:
    return GrowthMetricsFundamentals(
        period_end=period_end,
        eps_basic=eps_basic,
        eps_diluted=eps_diluted,
        revenue=revenue,
    )


def test_compute_growth_metrics_returns_positive_eps_and_revenue_growth() -> None:
    previous = _period(
        period_end=date(2024, 12, 31), eps_basic=1.10, eps_diluted=1.00, revenue=1000.0
    )
    current = _period(
        period_end=date(2025, 12, 31), eps_basic=1.65, eps_diluted=1.50, revenue=1200.0
    )

    result = compute_growth_metrics(current, previous)

    assert result.eps_basis == "diluted"
    assert result.eps_growth_ratio is not None
    assert result.revenue_growth_ratio is not None
    assert round(result.eps_growth_ratio, 4) == 0.5
    assert round(result.eps_growth_percent or 0.0, 2) == 50.0
    assert round(result.revenue_growth_ratio, 4) == 0.2
    assert round(result.revenue_growth_percent or 0.0, 2) == 20.0
    assert result.unavailable_metrics == []


def test_compute_growth_metrics_falls_back_to_basic_eps_when_diluted_unavailable() -> None:
    previous = _period(
        period_end=date(2024, 12, 31), eps_basic=2.00, eps_diluted=None, revenue=800.0
    )
    current = _period(
        period_end=date(2025, 12, 31), eps_basic=2.50, eps_diluted=None, revenue=880.0
    )

    result = compute_growth_metrics(current, previous)

    assert result.eps_basis == "basic"
    assert result.eps_growth_ratio is not None
    assert round(result.eps_growth_ratio, 4) == 0.25
    assert round(result.eps_growth_percent or 0.0, 2) == 25.0
    assert round(result.revenue_growth_percent or 0.0, 2) == 10.0


def test_compute_growth_metrics_marks_metrics_unavailable_for_invalid_bases() -> None:
    previous = _period(period_end=date(2024, 12, 31), eps_basic=1.00, eps_diluted=None, revenue=0.0)
    current = _period(
        period_end=date(2025, 12, 31), eps_basic=None, eps_diluted=1.30, revenue=140.0
    )

    result = compute_growth_metrics(current, previous)

    assert result.eps_basis == "unavailable"
    assert result.eps_growth_ratio is None
    assert result.revenue_growth_ratio is None
    assert "eps_growth" in result.unavailable_metrics
    assert "revenue_growth" in result.unavailable_metrics


def test_compute_growth_metrics_handles_negative_previous_values() -> None:
    previous = _period(
        period_end=date(2024, 12, 31), eps_basic=-2.0, eps_diluted=-2.0, revenue=-100.0
    )
    current = _period(
        period_end=date(2025, 12, 31), eps_basic=-1.0, eps_diluted=-1.0, revenue=-90.0
    )

    result = compute_growth_metrics(current, previous)

    assert result.eps_growth_ratio is not None
    assert result.revenue_growth_ratio is not None
    assert round(result.eps_growth_ratio, 4) == 0.5
    assert round(result.revenue_growth_ratio, 4) == 0.1


def test_compute_growth_metrics_series_sorts_and_computes_sequentially() -> None:
    periods = [
        _period(period_end=date(2025, 12, 31), eps_basic=1.65, eps_diluted=1.50, revenue=1200.0),
        _period(period_end=date(2023, 12, 31), eps_basic=0.70, eps_diluted=0.60, revenue=900.0),
        _period(period_end=date(2024, 12, 31), eps_basic=1.10, eps_diluted=1.00, revenue=1000.0),
    ]

    results = compute_growth_metrics_series(periods)

    assert [item.period_end for item in results] == [date(2024, 12, 31), date(2025, 12, 31)]
    assert round(results[0].eps_growth_ratio or 0.0, 4) == 0.6667
    assert round(results[1].revenue_growth_ratio or 0.0, 4) == 0.2


def test_compute_growth_metrics_series_returns_empty_for_single_period() -> None:
    periods = [
        _period(period_end=date(2025, 12, 31), eps_basic=1.65, eps_diluted=1.50, revenue=1200.0)
    ]

    assert compute_growth_metrics_series(periods) == []
