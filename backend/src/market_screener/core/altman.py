"""Altman Z-score computation for fundamentals distress-risk assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime


COMPONENT_ORDER = (
    "working_capital_to_assets",
    "retained_earnings_to_assets",
    "ebit_to_assets",
    "market_value_equity_to_liabilities",
    "sales_to_assets",
)

DISTRESS_CUTOFF = 1.81
SAFE_CUTOFF = 2.99


@dataclass(frozen=True)
class AltmanFundamentals:
    """Fundamentals inputs needed for Altman Z-score computation."""

    period_end: date
    total_assets: float | None
    current_assets: float | None
    current_liabilities: float | None
    retained_earnings: float | None
    ebit: float | None
    market_cap: float | None
    total_liabilities: float | None
    revenue: float | None


@dataclass(frozen=True)
class AltmanZScoreResult:
    """Computed Altman Z-score result for one period."""

    period_end: date
    z_score: float | None
    zone: str
    factors: dict[str, float | None]
    weighted_components: dict[str, float | None]
    unavailable_factors: list[str]
    diagnostics: dict[str, float | None]


def compute_altman_z_score(fundamentals: AltmanFundamentals) -> AltmanZScoreResult:
    """Compute Altman Z-score using the original public-manufacturing coefficients."""

    working_capital = _subtract(fundamentals.current_assets, fundamentals.current_liabilities)

    factor_working_capital = _safe_ratio(working_capital, fundamentals.total_assets)
    factor_retained_earnings = _safe_ratio(
        fundamentals.retained_earnings,
        fundamentals.total_assets,
    )
    factor_ebit = _safe_ratio(fundamentals.ebit, fundamentals.total_assets)
    factor_market_value_equity = _safe_ratio(
        fundamentals.market_cap,
        fundamentals.total_liabilities,
    )
    factor_sales = _safe_ratio(fundamentals.revenue, fundamentals.total_assets)

    factors = {
        "working_capital_to_assets": factor_working_capital,
        "retained_earnings_to_assets": factor_retained_earnings,
        "ebit_to_assets": factor_ebit,
        "market_value_equity_to_liabilities": factor_market_value_equity,
        "sales_to_assets": factor_sales,
    }
    unavailable_factors = [name for name in COMPONENT_ORDER if factors[name] is None]

    weighted_components = {
        "working_capital_to_assets": _weighted_value(factor_working_capital, 1.2),
        "retained_earnings_to_assets": _weighted_value(factor_retained_earnings, 1.4),
        "ebit_to_assets": _weighted_value(factor_ebit, 3.3),
        "market_value_equity_to_liabilities": _weighted_value(factor_market_value_equity, 0.6),
        "sales_to_assets": _weighted_value(factor_sales, 1.0),
    }

    if unavailable_factors:
        z_score: float | None = None
        zone = "unavailable"
    else:
        z_score = sum(
            weighted_components[name]
            for name in COMPONENT_ORDER
            if weighted_components[name] is not None
        )
        if z_score < DISTRESS_CUTOFF:
            zone = "distress"
        elif z_score <= SAFE_CUTOFF:
            zone = "grey"
        else:
            zone = "safe"

    diagnostics = {
        "working_capital": working_capital,
        "total_assets": fundamentals.total_assets,
        "total_liabilities": fundamentals.total_liabilities,
        "retained_earnings": fundamentals.retained_earnings,
        "ebit": fundamentals.ebit,
        "market_cap": fundamentals.market_cap,
        "revenue": fundamentals.revenue,
    }

    return AltmanZScoreResult(
        period_end=fundamentals.period_end,
        z_score=z_score,
        zone=zone,
        factors=factors,
        weighted_components=weighted_components,
        unavailable_factors=unavailable_factors,
        diagnostics=diagnostics,
    )


def compute_altman_z_score_series(periods: list[AltmanFundamentals]) -> list[AltmanZScoreResult]:
    """Compute Altman Z-score results for each supplied period in chronological order."""

    ordered = sorted(periods, key=lambda item: item.period_end)
    return [compute_altman_z_score(item) for item in ordered]


def _subtract(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator <= 0:
        return None
    return numerator / denominator


def _weighted_value(value: float | None, coefficient: float) -> float | None:
    if value is None:
        return None
    return coefficient * value


def main() -> None:
    """CLI entrypoint for Altman Z-score calculation smoke check."""

    fundamentals = AltmanFundamentals(
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
    result = compute_altman_z_score(fundamentals)
    now = datetime.now(UTC).isoformat()
    print(
        "altman_z_score:"
        f" ts={now}"
        f" period_end={result.period_end.isoformat()}"
        f" z_score={None if result.z_score is None else round(result.z_score, 4)}"
        f" zone={result.zone}"
        f" unavailable={len(result.unavailable_factors)}"
    )


if __name__ == "__main__":
    main()
