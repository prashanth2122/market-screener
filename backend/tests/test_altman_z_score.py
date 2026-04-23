"""Tests for Altman Z-score computation logic."""

from __future__ import annotations

from datetime import date

from market_screener.core.altman import (
    AltmanFundamentals,
    compute_altman_z_score,
    compute_altman_z_score_series,
)


def _period(
    *,
    period_end: date,
    total_assets: float | None,
    current_assets: float | None,
    current_liabilities: float | None,
    retained_earnings: float | None,
    ebit: float | None,
    market_cap: float | None,
    total_liabilities: float | None,
    revenue: float | None,
) -> AltmanFundamentals:
    return AltmanFundamentals(
        period_end=period_end,
        total_assets=total_assets,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        retained_earnings=retained_earnings,
        ebit=ebit,
        market_cap=market_cap,
        total_liabilities=total_liabilities,
        revenue=revenue,
    )


def test_compute_altman_z_score_returns_safe_zone_for_strong_profile() -> None:
    current = _period(
        period_end=date(2025, 12, 31),
        total_assets=1000.0,
        current_assets=520.0,
        current_liabilities=230.0,
        retained_earnings=280.0,
        ebit=170.0,
        market_cap=1400.0,
        total_liabilities=620.0,
        revenue=1500.0,
    )

    result = compute_altman_z_score(current)

    assert result.z_score is not None
    assert round(result.z_score, 4) == 4.8965
    assert result.zone == "safe"
    assert result.unavailable_factors == []


def test_compute_altman_z_score_returns_distress_zone_for_weak_profile() -> None:
    current = _period(
        period_end=date(2025, 12, 31),
        total_assets=1000.0,
        current_assets=180.0,
        current_liabilities=260.0,
        retained_earnings=-120.0,
        ebit=20.0,
        market_cap=160.0,
        total_liabilities=900.0,
        revenue=300.0,
    )

    result = compute_altman_z_score(current)

    assert result.z_score is not None
    assert round(result.z_score, 4) == 0.0987
    assert result.zone == "distress"
    assert result.unavailable_factors == []


def test_compute_altman_z_score_returns_grey_zone_for_mid_profile() -> None:
    current = _period(
        period_end=date(2025, 12, 31),
        total_assets=1000.0,
        current_assets=420.0,
        current_liabilities=260.0,
        retained_earnings=160.0,
        ebit=120.0,
        market_cap=600.0,
        total_liabilities=500.0,
        revenue=860.0,
    )

    result = compute_altman_z_score(current)

    assert result.z_score is not None
    assert round(result.z_score, 4) == 2.94
    assert result.zone == "grey"
    assert result.unavailable_factors == []


def test_compute_altman_z_score_marks_missing_inputs_unavailable() -> None:
    current = _period(
        period_end=date(2025, 12, 31),
        total_assets=1000.0,
        current_assets=None,
        current_liabilities=260.0,
        retained_earnings=160.0,
        ebit=120.0,
        market_cap=600.0,
        total_liabilities=500.0,
        revenue=None,
    )

    result = compute_altman_z_score(current)

    assert result.z_score is None
    assert result.zone == "unavailable"
    assert "working_capital_to_assets" in result.unavailable_factors
    assert "sales_to_assets" in result.unavailable_factors


def test_compute_altman_z_score_series_sorts_and_computes() -> None:
    periods = [
        _period(
            period_end=date(2025, 12, 31),
            total_assets=1000.0,
            current_assets=520.0,
            current_liabilities=230.0,
            retained_earnings=280.0,
            ebit=170.0,
            market_cap=1400.0,
            total_liabilities=620.0,
            revenue=1500.0,
        ),
        _period(
            period_end=date(2023, 12, 31),
            total_assets=1000.0,
            current_assets=150.0,
            current_liabilities=250.0,
            retained_earnings=-80.0,
            ebit=35.0,
            market_cap=200.0,
            total_liabilities=920.0,
            revenue=420.0,
        ),
        _period(
            period_end=date(2024, 12, 31),
            total_assets=1000.0,
            current_assets=420.0,
            current_liabilities=260.0,
            retained_earnings=160.0,
            ebit=120.0,
            market_cap=600.0,
            total_liabilities=500.0,
            revenue=860.0,
        ),
    ]

    results = compute_altman_z_score_series(periods)

    assert [item.period_end for item in results] == [
        date(2023, 12, 31),
        date(2024, 12, 31),
        date(2025, 12, 31),
    ]
    assert results[0].zone == "distress"
    assert results[1].zone == "grey"
    assert results[2].zone == "safe"
