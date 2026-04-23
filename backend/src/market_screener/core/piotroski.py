"""Piotroski F-score computation for fundamentals quality assessment."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime


CRITERIA_ORDER = (
    "positive_roa",
    "positive_operating_cash_flow",
    "improving_roa",
    "operating_cash_flow_exceeds_net_income",
    "lower_leverage",
    "improving_current_ratio",
    "no_new_share_dilution",
    "improving_gross_margin",
    "improving_asset_turnover",
)


@dataclass(frozen=True)
class PiotroskiFundamentals:
    """Fundamentals inputs needed for Piotroski F-score computation."""

    period_end: date
    net_income: float | None
    operating_cash_flow: float | None
    total_assets: float | None
    long_term_debt: float | None
    current_assets: float | None
    current_liabilities: float | None
    shares_outstanding: float | None
    gross_profit: float | None
    revenue: float | None


@dataclass(frozen=True)
class PiotroskiFScoreResult:
    """Computed Piotroski F-score result for one period."""

    period_end: date
    score: int
    criteria: dict[str, bool | None]
    passed_criteria: list[str]
    failed_criteria: list[str]
    unavailable_criteria: list[str]
    diagnostics: dict[str, float | None]


def compute_piotroski_f_score(
    current: PiotroskiFundamentals,
    previous: PiotroskiFundamentals,
) -> PiotroskiFScoreResult:
    """Compute Piotroski F-score from current and previous period fundamentals."""

    current_roa = _safe_ratio(current.net_income, current.total_assets)
    previous_roa = _safe_ratio(previous.net_income, previous.total_assets)
    current_leverage = _safe_ratio(current.long_term_debt, current.total_assets)
    previous_leverage = _safe_ratio(previous.long_term_debt, previous.total_assets)
    current_current_ratio = _safe_ratio(current.current_assets, current.current_liabilities)
    previous_current_ratio = _safe_ratio(previous.current_assets, previous.current_liabilities)
    current_gross_margin = _safe_ratio(current.gross_profit, current.revenue)
    previous_gross_margin = _safe_ratio(previous.gross_profit, previous.revenue)
    current_asset_turnover = _safe_ratio(current.revenue, current.total_assets)
    previous_asset_turnover = _safe_ratio(previous.revenue, previous.total_assets)

    criteria = {
        "positive_roa": _compare_unary(current_roa, lambda value: value > 0.0),
        "positive_operating_cash_flow": _compare_unary(
            current.operating_cash_flow,
            lambda value: value > 0.0,
        ),
        "improving_roa": _compare_binary(current_roa, previous_roa, lambda now, prior: now > prior),
        "operating_cash_flow_exceeds_net_income": _compare_binary(
            current.operating_cash_flow,
            current.net_income,
            lambda cash_flow, net_income: cash_flow > net_income,
        ),
        "lower_leverage": _compare_binary(
            current_leverage,
            previous_leverage,
            lambda now, prior: now < prior,
        ),
        "improving_current_ratio": _compare_binary(
            current_current_ratio,
            previous_current_ratio,
            lambda now, prior: now > prior,
        ),
        "no_new_share_dilution": _compare_binary(
            current.shares_outstanding,
            previous.shares_outstanding,
            lambda now, prior: now <= prior,
        ),
        "improving_gross_margin": _compare_binary(
            current_gross_margin,
            previous_gross_margin,
            lambda now, prior: now > prior,
        ),
        "improving_asset_turnover": _compare_binary(
            current_asset_turnover,
            previous_asset_turnover,
            lambda now, prior: now > prior,
        ),
    }

    passed_criteria = [name for name in CRITERIA_ORDER if criteria[name] is True]
    failed_criteria = [name for name in CRITERIA_ORDER if criteria[name] is False]
    unavailable_criteria = [name for name in CRITERIA_ORDER if criteria[name] is None]
    score = len(passed_criteria)

    diagnostics = {
        "current_roa": current_roa,
        "previous_roa": previous_roa,
        "current_leverage_ratio": current_leverage,
        "previous_leverage_ratio": previous_leverage,
        "current_ratio": current_current_ratio,
        "previous_current_ratio": previous_current_ratio,
        "current_gross_margin": current_gross_margin,
        "previous_gross_margin": previous_gross_margin,
        "current_asset_turnover": current_asset_turnover,
        "previous_asset_turnover": previous_asset_turnover,
    }

    return PiotroskiFScoreResult(
        period_end=current.period_end,
        score=score,
        criteria=criteria,
        passed_criteria=passed_criteria,
        failed_criteria=failed_criteria,
        unavailable_criteria=unavailable_criteria,
        diagnostics=diagnostics,
    )


def compute_piotroski_f_score_series(
    periods: list[PiotroskiFundamentals],
) -> list[PiotroskiFScoreResult]:
    """Compute Piotroski F-score for each period using the prior period as baseline."""

    if len(periods) < 2:
        return []
    ordered = sorted(periods, key=lambda item: item.period_end)
    return [
        compute_piotroski_f_score(ordered[index], ordered[index - 1])
        for index in range(1, len(ordered))
    ]


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator <= 0:
        return None
    return numerator / denominator


def _compare_unary(value: float | None, predicate: Callable[[float], bool]) -> bool | None:
    if value is None:
        return None
    return predicate(value)


def _compare_binary(
    left: float | None,
    right: float | None,
    predicate: Callable[[float, float], bool],
) -> bool | None:
    if left is None or right is None:
        return None
    return predicate(left, right)


def main() -> None:
    """CLI entrypoint for Piotroski F-score calculation smoke check."""

    current = PiotroskiFundamentals(
        period_end=date(2025, 12, 31),
        net_income=220.0,
        operating_cash_flow=260.0,
        total_assets=1000.0,
        long_term_debt=180.0,
        current_assets=420.0,
        current_liabilities=230.0,
        shares_outstanding=100.0,
        gross_profit=520.0,
        revenue=1200.0,
    )
    previous = PiotroskiFundamentals(
        period_end=date(2024, 12, 31),
        net_income=180.0,
        operating_cash_flow=190.0,
        total_assets=980.0,
        long_term_debt=210.0,
        current_assets=390.0,
        current_liabilities=240.0,
        shares_outstanding=101.0,
        gross_profit=460.0,
        revenue=1150.0,
    )
    result = compute_piotroski_f_score(current, previous)
    now = datetime.now(UTC).isoformat()
    print(
        "piotroski_f_score:"
        f" ts={now}"
        f" period_end={result.period_end.isoformat()}"
        f" score={result.score}"
        f" passed={len(result.passed_criteria)}"
        f" failed={len(result.failed_criteria)}"
        f" unavailable={len(result.unavailable_criteria)}"
    )


if __name__ == "__main__":
    main()
