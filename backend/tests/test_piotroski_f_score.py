"""Tests for Piotroski F-score computation logic."""

from __future__ import annotations

from datetime import date

from market_screener.core.piotroski import (
    compute_piotroski_f_score,
    compute_piotroski_f_score_series,
    PiotroskiFundamentals,
)


def _period(
    *,
    period_end: date,
    net_income: float | None,
    operating_cash_flow: float | None,
    total_assets: float | None,
    long_term_debt: float | None,
    current_assets: float | None,
    current_liabilities: float | None,
    shares_outstanding: float | None,
    gross_profit: float | None,
    revenue: float | None,
) -> PiotroskiFundamentals:
    return PiotroskiFundamentals(
        period_end=period_end,
        net_income=net_income,
        operating_cash_flow=operating_cash_flow,
        total_assets=total_assets,
        long_term_debt=long_term_debt,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        shares_outstanding=shares_outstanding,
        gross_profit=gross_profit,
        revenue=revenue,
    )


def test_compute_piotroski_f_score_returns_full_score_when_all_signals_improve() -> None:
    previous = _period(
        period_end=date(2024, 12, 31),
        net_income=100.0,
        operating_cash_flow=110.0,
        total_assets=900.0,
        long_term_debt=250.0,
        current_assets=300.0,
        current_liabilities=200.0,
        shares_outstanding=110.0,
        gross_profit=300.0,
        revenue=1000.0,
    )
    current = _period(
        period_end=date(2025, 12, 31),
        net_income=180.0,
        operating_cash_flow=220.0,
        total_assets=950.0,
        long_term_debt=180.0,
        current_assets=380.0,
        current_liabilities=200.0,
        shares_outstanding=108.0,
        gross_profit=420.0,
        revenue=1200.0,
    )

    result = compute_piotroski_f_score(current, previous)

    assert result.score == 9
    assert len(result.passed_criteria) == 9
    assert result.failed_criteria == []
    assert result.unavailable_criteria == []


def test_compute_piotroski_f_score_returns_zero_when_all_signals_worsen() -> None:
    previous = _period(
        period_end=date(2024, 12, 31),
        net_income=160.0,
        operating_cash_flow=170.0,
        total_assets=900.0,
        long_term_debt=150.0,
        current_assets=400.0,
        current_liabilities=200.0,
        shares_outstanding=100.0,
        gross_profit=450.0,
        revenue=1100.0,
    )
    current = _period(
        period_end=date(2025, 12, 31),
        net_income=-10.0,
        operating_cash_flow=-20.0,
        total_assets=1000.0,
        long_term_debt=300.0,
        current_assets=180.0,
        current_liabilities=220.0,
        shares_outstanding=110.0,
        gross_profit=320.0,
        revenue=1200.0,
    )

    result = compute_piotroski_f_score(current, previous)

    assert result.score == 0
    assert result.passed_criteria == []
    assert len(result.failed_criteria) == 9
    assert result.unavailable_criteria == []


def test_compute_piotroski_f_score_marks_missing_criteria_unavailable() -> None:
    previous = _period(
        period_end=date(2024, 12, 31),
        net_income=100.0,
        operating_cash_flow=100.0,
        total_assets=800.0,
        long_term_debt=None,
        current_assets=300.0,
        current_liabilities=None,
        shares_outstanding=None,
        gross_profit=250.0,
        revenue=900.0,
    )
    current = _period(
        period_end=date(2025, 12, 31),
        net_income=120.0,
        operating_cash_flow=None,
        total_assets=850.0,
        long_term_debt=100.0,
        current_assets=340.0,
        current_liabilities=220.0,
        shares_outstanding=100.0,
        gross_profit=290.0,
        revenue=None,
    )

    result = compute_piotroski_f_score(current, previous)

    assert result.score >= 1
    assert "positive_operating_cash_flow" in result.unavailable_criteria
    assert "lower_leverage" in result.unavailable_criteria
    assert "improving_current_ratio" in result.unavailable_criteria
    assert "no_new_share_dilution" in result.unavailable_criteria
    assert "improving_gross_margin" in result.unavailable_criteria
    assert "improving_asset_turnover" in result.unavailable_criteria


def test_compute_piotroski_f_score_series_sorts_and_computes_sequentially() -> None:
    periods = [
        _period(
            period_end=date(2025, 12, 31),
            net_income=180.0,
            operating_cash_flow=220.0,
            total_assets=950.0,
            long_term_debt=180.0,
            current_assets=380.0,
            current_liabilities=200.0,
            shares_outstanding=108.0,
            gross_profit=420.0,
            revenue=1200.0,
        ),
        _period(
            period_end=date(2023, 12, 31),
            net_income=70.0,
            operating_cash_flow=90.0,
            total_assets=850.0,
            long_term_debt=260.0,
            current_assets=280.0,
            current_liabilities=220.0,
            shares_outstanding=112.0,
            gross_profit=240.0,
            revenue=930.0,
        ),
        _period(
            period_end=date(2024, 12, 31),
            net_income=100.0,
            operating_cash_flow=110.0,
            total_assets=900.0,
            long_term_debt=250.0,
            current_assets=300.0,
            current_liabilities=200.0,
            shares_outstanding=110.0,
            gross_profit=300.0,
            revenue=1000.0,
        ),
    ]

    results = compute_piotroski_f_score_series(periods)

    assert [item.period_end for item in results] == [date(2024, 12, 31), date(2025, 12, 31)]
    assert results[0].score >= 5
    assert results[1].score == 9


def test_compute_piotroski_f_score_series_returns_empty_for_single_period() -> None:
    periods = [
        _period(
            period_end=date(2025, 12, 31),
            net_income=180.0,
            operating_cash_flow=220.0,
            total_assets=950.0,
            long_term_debt=180.0,
            current_assets=380.0,
            current_liabilities=200.0,
            shares_outstanding=108.0,
            gross_profit=420.0,
            revenue=1200.0,
        )
    ]

    assert compute_piotroski_f_score_series(periods) == []
