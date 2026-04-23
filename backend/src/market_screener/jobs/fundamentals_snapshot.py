"""Fundamentals snapshot pull workflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.core.timezone import normalize_to_utc
from market_screener.db.models.core import Asset, FundamentalsSnapshot
from market_screener.db.session import SessionFactory, create_session_factory_from_settings
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.idempotency import build_idempotency_key
from market_screener.providers.fmp import FMPFundamentalsClient

logger = logging.getLogger("market_screener.jobs.fundamentals_snapshot")


class FundamentalsSnapshotParseError(ValueError):
    """Raised when fundamentals payloads cannot be normalized."""


@dataclass(frozen=True)
class FundamentalsSnapshotPullResult:
    """Outcome summary for one fundamentals snapshot pull run."""

    requested_assets: int
    processed_assets: int
    failed_assets: int
    no_data_assets: int
    snapshots_written: int
    snapshots_skipped: int
    period_type: str
    snapshot_source: str
    idempotent_skip: bool = False


@dataclass(frozen=True)
class _FundamentalsRowPayload:
    period_end: date
    filing_date: date | None
    statement_currency: str | None
    revenue: Decimal | None
    gross_profit: Decimal | None
    ebit: Decimal | None
    net_income: Decimal | None
    operating_cash_flow: Decimal | None
    total_assets: Decimal | None
    total_liabilities: Decimal | None
    current_assets: Decimal | None
    current_liabilities: Decimal | None
    long_term_debt: Decimal | None
    retained_earnings: Decimal | None
    shares_outstanding: Decimal | None
    market_cap: Decimal | None
    eps_basic: Decimal | None
    eps_diluted: Decimal | None
    details: dict[str, Any]


class FundamentalsSnapshotPullJob:
    """Fetch and persist fundamentals snapshots for active equity assets."""

    def __init__(
        self,
        session_factory: SessionFactory,
        fundamentals_client_factory: Any,
        *,
        symbol_limit: int,
        period_type: str,
        limit_per_symbol: int,
        snapshot_source: str,
    ) -> None:
        normalized_period = period_type.strip().lower()
        if normalized_period not in {"annual", "quarter"}:
            raise ValueError("fundamentals_period_type_must_be_annual_or_quarter")
        self._session_factory = session_factory
        self._fundamentals_client_factory = fundamentals_client_factory
        self._symbol_limit = max(1, symbol_limit)
        self._period_type = normalized_period
        self._limit_per_symbol = max(1, limit_per_symbol)
        self._snapshot_source = snapshot_source.strip() or "fmp_v1"

    def run(self, *, now_utc: datetime | None = None) -> FundamentalsSnapshotPullResult:
        """Pull fundamentals snapshots and persist normalized rows."""

        reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
        with self._session_factory() as session:
            assets = list(
                session.scalars(
                    select(Asset)
                    .where(Asset.asset_type == "equity", Asset.active.is_(True))
                    .order_by(Asset.symbol.asc())
                    .limit(self._symbol_limit)
                ).all()
            )

        processed_assets = 0
        failed_assets = 0
        no_data_assets = 0
        snapshots_written = 0
        snapshots_skipped = 0

        with self._fundamentals_client_factory() as client:
            for asset in assets:
                try:
                    income_rows = client.get_income_statements(
                        asset.symbol,
                        period=self._period_type,
                        limit=self._limit_per_symbol,
                    )
                    balance_rows = client.get_balance_sheet_statements(
                        asset.symbol,
                        period=self._period_type,
                        limit=self._limit_per_symbol,
                    )
                    cash_flow_rows = client.get_cash_flow_statements(
                        asset.symbol,
                        period=self._period_type,
                        limit=self._limit_per_symbol,
                    )
                    metrics_rows = client.get_key_metrics(
                        asset.symbol,
                        period=self._period_type,
                        limit=self._limit_per_symbol,
                    )

                    snapshots = _merge_fundamentals_rows(
                        income_rows=income_rows,
                        balance_rows=balance_rows,
                        cash_flow_rows=cash_flow_rows,
                        metrics_rows=metrics_rows,
                        period_type=self._period_type,
                        limit_per_symbol=self._limit_per_symbol,
                    )
                    processed_assets += 1
                except Exception:
                    failed_assets += 1
                    logger.exception(
                        "fundamentals_snapshot_asset_failed",
                        extra={
                            "asset_id": asset.id,
                            "symbol": asset.symbol,
                            "period_type": self._period_type,
                        },
                    )
                    continue

                if not snapshots:
                    no_data_assets += 1
                    continue

                written, skipped = _persist_fundamentals_snapshots(
                    self._session_factory,
                    asset_id=asset.id,
                    period_type=self._period_type,
                    source=self._snapshot_source,
                    as_of_ts=reference_now,
                    snapshots=snapshots,
                )
                snapshots_written += written
                snapshots_skipped += skipped

        return FundamentalsSnapshotPullResult(
            requested_assets=len(assets),
            processed_assets=processed_assets,
            failed_assets=failed_assets,
            no_data_assets=no_data_assets,
            snapshots_written=snapshots_written,
            snapshots_skipped=snapshots_skipped,
            period_type=self._period_type,
            snapshot_source=self._snapshot_source,
        )


def run_fundamentals_snapshot_pull(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    now_utc: datetime | None = None,
) -> FundamentalsSnapshotPullResult:
    """Run fundamentals snapshot pull with default runtime wiring."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    reference_now = normalize_to_utc(now_utc or datetime.now(UTC))
    window_anchor = reference_now.date().isoformat()
    symbol_fingerprint = _active_equity_symbol_fingerprint(resolved_session_factory)
    idempotency_key = build_idempotency_key(
        "fundamentals_snapshot_pull",
        {
            "period_type": resolved_settings.fundamentals_snapshot_period_type,
            "limit_per_symbol": resolved_settings.fundamentals_snapshot_limit_per_symbol,
            "snapshot_source": resolved_settings.fundamentals_snapshot_source,
            "window_anchor": window_anchor,
            "symbol_fingerprint": symbol_fingerprint,
        },
    )

    if resolved_audit.has_completed_run("fundamentals_snapshot_pull", idempotency_key):
        return FundamentalsSnapshotPullResult(
            requested_assets=0,
            processed_assets=0,
            failed_assets=0,
            no_data_assets=0,
            snapshots_written=0,
            snapshots_skipped=0,
            period_type=resolved_settings.fundamentals_snapshot_period_type,
            snapshot_source=resolved_settings.fundamentals_snapshot_source,
            idempotent_skip=True,
        )

    def _client_factory() -> FMPFundamentalsClient:
        return FMPFundamentalsClient.from_settings(resolved_settings)

    job = FundamentalsSnapshotPullJob(
        resolved_session_factory,
        _client_factory,
        symbol_limit=resolved_settings.fundamentals_snapshot_symbol_limit,
        period_type=resolved_settings.fundamentals_snapshot_period_type,
        limit_per_symbol=resolved_settings.fundamentals_snapshot_limit_per_symbol,
        snapshot_source=resolved_settings.fundamentals_snapshot_source,
    )
    with resolved_audit.track_job_run(
        "fundamentals_snapshot_pull",
        details={
            "provider": "fmp",
            "symbol_limit": resolved_settings.fundamentals_snapshot_symbol_limit,
            "period_type": resolved_settings.fundamentals_snapshot_period_type,
            "limit_per_symbol": resolved_settings.fundamentals_snapshot_limit_per_symbol,
            "snapshot_source": resolved_settings.fundamentals_snapshot_source,
            "window_anchor": window_anchor,
            "symbol_fingerprint": symbol_fingerprint,
            "idempotency_key": idempotency_key,
            "idempotency_hit": False,
        },
        idempotency_key=idempotency_key,
    ) as run_handle:
        result = job.run(now_utc=reference_now)
        run_handle.add_details(
            {
                "requested_assets": result.requested_assets,
                "processed_assets": result.processed_assets,
                "failed_assets": result.failed_assets,
                "no_data_assets": result.no_data_assets,
                "snapshots_written": result.snapshots_written,
                "snapshots_skipped": result.snapshots_skipped,
                "period_type": result.period_type,
                "snapshot_source": result.snapshot_source,
                "idempotent_skip": False,
            }
        )
        return result


def _active_equity_symbol_fingerprint(session_factory: SessionFactory) -> str:
    with session_factory() as session:
        symbols = sorted(
            session.scalars(
                select(Asset.symbol).where(Asset.asset_type == "equity", Asset.active.is_(True))
            ).all()
        )
    if not symbols:
        return "none"
    return "|".join(symbols)


def _persist_fundamentals_snapshots(
    session_factory: SessionFactory,
    *,
    asset_id: int,
    period_type: str,
    source: str,
    as_of_ts: datetime,
    snapshots: list[_FundamentalsRowPayload],
) -> tuple[int, int]:
    if not snapshots:
        return 0, 0

    period_ends = [item.period_end for item in snapshots]
    with session_factory() as session:
        existing_period_ends = set(
            session.scalars(
                select(FundamentalsSnapshot.period_end).where(
                    FundamentalsSnapshot.asset_id == asset_id,
                    FundamentalsSnapshot.period_type == period_type,
                    FundamentalsSnapshot.source == source,
                    FundamentalsSnapshot.period_end.in_(period_ends),
                )
            ).all()
        )

        written = 0
        skipped = 0
        for item in snapshots:
            if item.period_end in existing_period_ends:
                skipped += 1
                continue
            session.add(
                FundamentalsSnapshot(
                    asset_id=asset_id,
                    as_of_ts=as_of_ts,
                    period_type=period_type,
                    period_end=item.period_end,
                    filing_date=item.filing_date,
                    statement_currency=item.statement_currency,
                    revenue=item.revenue,
                    gross_profit=item.gross_profit,
                    ebit=item.ebit,
                    net_income=item.net_income,
                    operating_cash_flow=item.operating_cash_flow,
                    total_assets=item.total_assets,
                    total_liabilities=item.total_liabilities,
                    current_assets=item.current_assets,
                    current_liabilities=item.current_liabilities,
                    long_term_debt=item.long_term_debt,
                    retained_earnings=item.retained_earnings,
                    shares_outstanding=item.shares_outstanding,
                    market_cap=item.market_cap,
                    eps_basic=item.eps_basic,
                    eps_diluted=item.eps_diluted,
                    source=source,
                    details=item.details,
                )
            )
            existing_period_ends.add(item.period_end)
            written += 1
        session.commit()

    return written, skipped


def _merge_fundamentals_rows(
    *,
    income_rows: list[dict[str, Any]],
    balance_rows: list[dict[str, Any]],
    cash_flow_rows: list[dict[str, Any]],
    metrics_rows: list[dict[str, Any]],
    period_type: str,
    limit_per_symbol: int,
) -> list[_FundamentalsRowPayload]:
    income_by_date = _index_rows_by_period_date(income_rows)
    balance_by_date = _index_rows_by_period_date(balance_rows)
    cash_flow_by_date = _index_rows_by_period_date(cash_flow_rows)
    metrics_by_date = _index_rows_by_period_date(metrics_rows)

    all_dates = sorted(
        set(income_by_date) | set(balance_by_date) | set(cash_flow_by_date) | set(metrics_by_date),
        reverse=True,
    )[:limit_per_symbol]

    payloads: list[_FundamentalsRowPayload] = []
    for period_end in all_dates:
        income = income_by_date.get(period_end)
        balance = balance_by_date.get(period_end)
        cash_flow = cash_flow_by_date.get(period_end)
        metrics = metrics_by_date.get(period_end)
        if income is None and balance is None and cash_flow is None and metrics is None:
            continue

        payloads.append(
            _FundamentalsRowPayload(
                period_end=period_end,
                filing_date=_parse_date(
                    _first_value(income, ("fillingDate", "filingDate", "acceptedDate"))
                ),
                statement_currency=_to_optional_str(
                    _first_value(
                        income,
                        ("reportedCurrency",),
                        fallback_row=balance,
                        fallback_keys=("reportedCurrency",),
                    )
                ),
                revenue=_to_decimal(_first_value(income, ("revenue",))),
                gross_profit=_to_decimal(_first_value(income, ("grossProfit",))),
                ebit=_to_decimal(_first_value(income, ("ebit",))),
                net_income=_to_decimal(_first_value(income, ("netIncome",))),
                operating_cash_flow=_to_decimal(_first_value(cash_flow, ("operatingCashFlow",))),
                total_assets=_to_decimal(_first_value(balance, ("totalAssets",))),
                total_liabilities=_to_decimal(_first_value(balance, ("totalLiabilities",))),
                current_assets=_to_decimal(_first_value(balance, ("totalCurrentAssets",))),
                current_liabilities=_to_decimal(
                    _first_value(balance, ("totalCurrentLiabilities",))
                ),
                long_term_debt=_to_decimal(
                    _first_value(balance, ("longTermDebt", "longTermDebtNoncurrent"))
                ),
                retained_earnings=_to_decimal(_first_value(balance, ("retainedEarnings",))),
                shares_outstanding=_to_decimal(
                    _first_value(
                        metrics,
                        ("sharesOutstanding",),
                        fallback_row=income,
                        fallback_keys=("weightedAverageShsOut", "weightedAverageShsOutDil"),
                    )
                ),
                market_cap=_to_decimal(
                    _first_value(metrics, ("marketCap", "marketCapTTM", "marketCapitalization"))
                ),
                eps_basic=_to_decimal(_first_value(income, ("eps", "epsBasic"))),
                eps_diluted=_to_decimal(_first_value(income, ("epsdiluted", "epsDiluted"))),
                details={
                    "provider": "fmp",
                    "period_type": period_type,
                    "has_income": income is not None,
                    "has_balance": balance is not None,
                    "has_cash_flow": cash_flow is not None,
                    "has_metrics": metrics is not None,
                },
            )
        )

    return payloads


def _index_rows_by_period_date(rows: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    indexed: dict[date, dict[str, Any]] = {}
    for row in rows:
        date_value = _first_value(row, ("date", "calendarYear"))
        period_end = _parse_date(date_value)
        if period_end is None:
            continue
        indexed.setdefault(period_end, row)
    return indexed


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, int):
        if 1900 <= value <= 2200:
            return date(value, 12, 31)
        return None
    text = str(value).strip()
    if not text:
        return None
    if " " in text:
        text = text.split(" ", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _first_value(
    row: dict[str, Any] | None,
    keys: tuple[str, ...],
    *,
    fallback_row: dict[str, Any] | None = None,
    fallback_keys: tuple[str, ...] = (),
) -> Any:
    if row:
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
    if fallback_row:
        for key in fallback_keys:
            if key in fallback_row and fallback_row[key] is not None:
                return fallback_row[key]
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def main() -> None:
    """CLI entrypoint for manual fundamentals snapshot pull runs."""

    result = run_fundamentals_snapshot_pull()
    logger.info(
        "fundamentals_snapshot_pull_completed",
        extra={
            "requested_assets": result.requested_assets,
            "processed_assets": result.processed_assets,
            "failed_assets": result.failed_assets,
            "no_data_assets": result.no_data_assets,
            "snapshots_written": result.snapshots_written,
            "snapshots_skipped": result.snapshots_skipped,
            "period_type": result.period_type,
            "snapshot_source": result.snapshot_source,
            "idempotent_skip": result.idempotent_skip,
        },
    )
    print(
        "fundamentals_snapshot_pull:"
        f" requested_assets={result.requested_assets}"
        f" processed_assets={result.processed_assets}"
        f" failed_assets={result.failed_assets}"
        f" no_data_assets={result.no_data_assets}"
        f" snapshots_written={result.snapshots_written}"
        f" snapshots_skipped={result.snapshots_skipped}"
        f" period_type={result.period_type}"
        f" snapshot_source={result.snapshot_source}"
        f" idempotent_skip={result.idempotent_skip}"
    )


if __name__ == "__main__":
    main()
