"""Tests for fundamentals quality normalization (0-100)."""

from __future__ import annotations

from datetime import date

from market_screener.core.fundamentals_quality import (
    FundamentalsQualityInputs,
    compute_fundamentals_quality_score,
    compute_fundamentals_quality_score_series,
)


def _period(
    *,
    period_end: date,
    piotroski_score: int | None,
    altman_z_score: float | None,
    altman_zone: str | None,
    eps_growth_percent: float | None,
    revenue_growth_percent: float | None,
    roe: float | None,
    debt_to_equity: float | None,
) -> FundamentalsQualityInputs:
    return FundamentalsQualityInputs(
        period_end=period_end,
        piotroski_score=piotroski_score,
        altman_z_score=altman_z_score,
        altman_zone=altman_zone,
        eps_growth_percent=eps_growth_percent,
        revenue_growth_percent=revenue_growth_percent,
        roe=roe,
        debt_to_equity=debt_to_equity,
    )


def test_compute_fundamentals_quality_score_returns_weighted_normalized_score() -> None:
    inputs = _period(
        period_end=date(2025, 12, 31),
        piotroski_score=7,
        altman_z_score=3.2,
        altman_zone=None,
        eps_growth_percent=18.0,
        revenue_growth_percent=12.0,
        roe=17.0,
        debt_to_equity=0.9,
    )

    result = compute_fundamentals_quality_score(inputs)

    assert result.score is not None
    assert round(result.score, 2) == 72.81
    assert result.unavailable_components == []
    assert round(sum(result.effective_weights.values()), 6) == 1.0


def test_compute_fundamentals_quality_score_reweights_when_some_components_missing() -> None:
    inputs = _period(
        period_end=date(2025, 12, 31),
        piotroski_score=9,
        altman_z_score=None,
        altman_zone="safe",
        eps_growth_percent=None,
        revenue_growth_percent=None,
        roe=None,
        debt_to_equity=None,
    )

    result = compute_fundamentals_quality_score(inputs)

    assert result.score is not None
    assert round(result.score, 2) == 93.18
    assert set(result.unavailable_components) == {"growth", "roe", "debt_discipline"}
    assert round(result.effective_weights["piotroski"], 6) == round(0.3 / 0.55, 6)
    assert round(result.effective_weights["altman"], 6) == round(0.25 / 0.55, 6)


def test_compute_fundamentals_quality_score_returns_none_when_every_component_missing() -> None:
    inputs = _period(
        period_end=date(2025, 12, 31),
        piotroski_score=None,
        altman_z_score=None,
        altman_zone=None,
        eps_growth_percent=None,
        revenue_growth_percent=None,
        roe=None,
        debt_to_equity=None,
    )

    result = compute_fundamentals_quality_score(inputs)

    assert result.score is None
    assert len(result.unavailable_components) == 5
    assert all(value == 0.0 for value in result.effective_weights.values())


def test_compute_fundamentals_quality_score_clamps_growth_extremes() -> None:
    inputs = _period(
        period_end=date(2025, 12, 31),
        piotroski_score=None,
        altman_z_score=None,
        altman_zone=None,
        eps_growth_percent=-80.0,
        revenue_growth_percent=120.0,
        roe=None,
        debt_to_equity=None,
    )

    result = compute_fundamentals_quality_score(inputs)

    assert result.component_scores["growth"] == 50.0
    assert result.score == 50.0


def test_compute_fundamentals_quality_score_accepts_roe_ratio_inputs() -> None:
    inputs = _period(
        period_end=date(2025, 12, 31),
        piotroski_score=None,
        altman_z_score=None,
        altman_zone=None,
        eps_growth_percent=None,
        revenue_growth_percent=None,
        roe=0.18,
        debt_to_equity=None,
    )

    result = compute_fundamentals_quality_score(inputs)

    assert result.component_scores["roe"] == 72.0
    assert result.score == 72.0


def test_compute_fundamentals_quality_score_prefers_altman_z_over_zone_fallback() -> None:
    inputs = _period(
        period_end=date(2025, 12, 31),
        piotroski_score=None,
        altman_z_score=3.5,
        altman_zone="distress",
        eps_growth_percent=None,
        revenue_growth_percent=None,
        roe=None,
        debt_to_equity=None,
    )

    result = compute_fundamentals_quality_score(inputs)

    assert result.component_scores["altman"] is not None
    assert round(result.component_scores["altman"] or 0.0, 2) == 75.08
    assert result.score is not None
    assert round(result.score, 2) == 75.08


def test_compute_fundamentals_quality_score_series_sorts_periods() -> None:
    periods = [
        _period(
            period_end=date(2025, 12, 31),
            piotroski_score=7,
            altman_z_score=3.2,
            altman_zone=None,
            eps_growth_percent=18.0,
            revenue_growth_percent=12.0,
            roe=17.0,
            debt_to_equity=0.9,
        ),
        _period(
            period_end=date(2023, 12, 31),
            piotroski_score=3,
            altman_z_score=1.0,
            altman_zone=None,
            eps_growth_percent=-12.0,
            revenue_growth_percent=-5.0,
            roe=4.0,
            debt_to_equity=2.8,
        ),
        _period(
            period_end=date(2024, 12, 31),
            piotroski_score=5,
            altman_z_score=2.5,
            altman_zone=None,
            eps_growth_percent=8.0,
            revenue_growth_percent=6.0,
            roe=11.0,
            debt_to_equity=1.4,
        ),
    ]

    results = compute_fundamentals_quality_score_series(periods)

    assert [item.period_end for item in results] == [
        date(2023, 12, 31),
        date(2024, 12, 31),
        date(2025, 12, 31),
    ]
    assert results[0].score is not None
    assert results[1].score is not None
    assert results[2].score is not None
    assert results[0].score < results[1].score < results[2].score
