"""Fundamentals quality normalization to a 0-100 score."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime


COMPONENT_ORDER = (
    "piotroski",
    "altman",
    "growth",
    "roe",
    "debt_discipline",
)

COMPONENT_WEIGHTS = {
    "piotroski": 0.30,
    "altman": 0.25,
    "growth": 0.25,
    "roe": 0.10,
    "debt_discipline": 0.10,
}


@dataclass(frozen=True)
class FundamentalsQualityInputs:
    """Inputs needed to normalize fundamentals quality to 0-100."""

    period_end: date
    piotroski_score: int | None
    altman_z_score: float | None
    altman_zone: str | None
    eps_growth_percent: float | None
    revenue_growth_percent: float | None
    roe: float | None
    debt_to_equity: float | None


@dataclass(frozen=True)
class FundamentalsQualityScoreResult:
    """Normalized fundamentals quality result for one period."""

    period_end: date
    score: float | None
    component_scores: dict[str, float | None]
    configured_weights: dict[str, float]
    effective_weights: dict[str, float]
    unavailable_components: list[str]
    diagnostics: dict[str, float | str | None]


def compute_fundamentals_quality_score(
    inputs: FundamentalsQualityInputs,
) -> FundamentalsQualityScoreResult:
    """Compute normalized fundamentals quality score on a 0-100 scale."""

    component_scores = {
        "piotroski": _piotroski_to_score(inputs.piotroski_score),
        "altman": _altman_to_score(inputs.altman_z_score, inputs.altman_zone),
        "growth": _growth_to_score(
            eps_growth_percent=inputs.eps_growth_percent,
            revenue_growth_percent=inputs.revenue_growth_percent,
        ),
        "roe": _roe_to_score(inputs.roe),
        "debt_discipline": _debt_to_equity_to_score(inputs.debt_to_equity),
    }
    unavailable_components = [name for name in COMPONENT_ORDER if component_scores[name] is None]

    available_weight_sum = sum(
        COMPONENT_WEIGHTS[name] for name in COMPONENT_ORDER if component_scores[name] is not None
    )

    if available_weight_sum <= 0:
        normalized_score: float | None = None
        effective_weights = {name: 0.0 for name in COMPONENT_ORDER}
    else:
        effective_weights = {
            name: (
                0.0
                if component_scores[name] is None
                else COMPONENT_WEIGHTS[name] / available_weight_sum
            )
            for name in COMPONENT_ORDER
        }
        normalized_score = sum(
            (component_scores[name] or 0.0) * effective_weights[name] for name in COMPONENT_ORDER
        )

    diagnostics: dict[str, float | str | None] = {
        "piotroski_raw": None if inputs.piotroski_score is None else float(inputs.piotroski_score),
        "altman_z_raw": inputs.altman_z_score,
        "altman_zone_raw": (inputs.altman_zone or "").strip().lower() or None,
        "eps_growth_pct_raw": inputs.eps_growth_percent,
        "revenue_growth_pct_raw": inputs.revenue_growth_percent,
        "roe_raw": inputs.roe,
        "debt_to_equity_raw": inputs.debt_to_equity,
        "available_weight_sum": available_weight_sum,
    }

    return FundamentalsQualityScoreResult(
        period_end=inputs.period_end,
        score=normalized_score,
        component_scores=component_scores,
        configured_weights=dict(COMPONENT_WEIGHTS),
        effective_weights=effective_weights,
        unavailable_components=unavailable_components,
        diagnostics=diagnostics,
    )


def compute_fundamentals_quality_score_series(
    periods: list[FundamentalsQualityInputs],
) -> list[FundamentalsQualityScoreResult]:
    """Compute normalized fundamentals quality for each period chronologically."""

    ordered = sorted(periods, key=lambda item: item.period_end)
    return [compute_fundamentals_quality_score(item) for item in ordered]


def _piotroski_to_score(value: int | None) -> float | None:
    if value is None:
        return None
    return _clamp(100.0 * (value / 9.0))


def _altman_to_score(z_score: float | None, zone: str | None) -> float | None:
    if z_score is not None:
        # Map three classic bands to 0-100 continuously:
        # distress (<1.81), grey (1.81-2.99), safe (>2.99).
        if z_score < 1.81:
            return _clamp(_linear_map(z_score, -1.0, 1.81, 0.0, 40.0))
        if z_score <= 2.99:
            return _clamp(_linear_map(z_score, 1.81, 2.99, 40.0, 70.0))
        return _clamp(_linear_map(z_score, 2.99, 6.0, 70.0, 100.0))

    normalized_zone = (zone or "").strip().lower()
    if normalized_zone == "distress":
        return 25.0
    if normalized_zone == "grey":
        return 55.0
    if normalized_zone == "safe":
        return 85.0
    return None


def _growth_to_score(
    *,
    eps_growth_percent: float | None,
    revenue_growth_percent: float | None,
) -> float | None:
    eps_score = _growth_percent_to_score(eps_growth_percent)
    revenue_score = _growth_percent_to_score(revenue_growth_percent)
    available = [value for value in (eps_score, revenue_score) if value is not None]
    if not available:
        return None
    return sum(available) / len(available)


def _growth_percent_to_score(value: float | None) -> float | None:
    if value is None:
        return None
    # -50% maps to 0, 0% maps to 50, +50% maps to 100 (clamped beyond bounds).
    return _clamp(value + 50.0)


def _roe_to_score(value: float | None) -> float | None:
    if value is None:
        return None
    normalized_pct = value * 100.0 if -1.0 <= value <= 1.0 else value
    # 0% maps to 0, 25%+ maps to 100 (clamped).
    return _clamp(normalized_pct * 4.0)


def _debt_to_equity_to_score(value: float | None) -> float | None:
    if value is None:
        return None
    # Lower leverage scores better. <=0.5 is excellent; >=3.0 is poor.
    if value <= 0.5:
        return 100.0
    if value >= 3.0:
        return 0.0
    return _clamp(_linear_map(value, 0.5, 3.0, 100.0, 0.0))


def _linear_map(
    value: float,
    source_min: float,
    source_max: float,
    target_min: float,
    target_max: float,
) -> float:
    if source_max <= source_min:
        return target_min
    ratio = (value - source_min) / (source_max - source_min)
    return target_min + ratio * (target_max - target_min)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def main() -> None:
    """CLI entrypoint for fundamentals quality normalization smoke check."""

    result = compute_fundamentals_quality_score(
        FundamentalsQualityInputs(
            period_end=date(2025, 12, 31),
            piotroski_score=7,
            altman_z_score=3.2,
            altman_zone=None,
            eps_growth_percent=18.0,
            revenue_growth_percent=12.0,
            roe=17.0,
            debt_to_equity=0.9,
        )
    )
    now = datetime.now(UTC).isoformat()
    print(
        "fundamentals_quality:"
        f" ts={now}"
        f" period_end={result.period_end.isoformat()}"
        f" score={None if result.score is None else round(result.score, 2)}"
        f" unavailable={len(result.unavailable_components)}"
    )


if __name__ == "__main__":
    main()
