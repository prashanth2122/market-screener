"""Retry workflow for persisted ingestion failures."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from market_screener.core.settings import Settings, get_settings
from market_screener.db.models.core import Asset
from market_screener.db.session import (
    SessionFactory,
    create_session_factory_from_settings,
)
from market_screener.jobs.audit import JobAuditTrail
from market_screener.jobs.equity_ohlcv import (
    _persist_candles_for_asset,
    normalize_finnhub_candles,
)
from market_screener.jobs.ingestion_failures import (
    IngestionFailureItem,
    IngestionFailureStore,
)
from market_screener.providers.finnhub import FinnhubClient

logger = logging.getLogger("market_screener.jobs.ingestion_retry")


@dataclass(frozen=True)
class IngestionRetryResult:
    """Summary of one ingestion retry workflow pass."""

    due_failures: int
    attempted: int
    retried_success: int
    retried_no_data: int
    retry_failed: int
    dead_lettered: int


class IngestionFailureRetryJob:
    """Replay due ingestion failures from the failure table."""

    def __init__(
        self,
        session_factory: SessionFactory,
        failure_store: IngestionFailureStore,
        finnhub_client_factory: Callable[[], FinnhubClient],
        *,
        default_resolution: str,
        default_lookback_days: int,
        batch_size: int,
    ) -> None:
        self._session_factory = session_factory
        self._failure_store = failure_store
        self._finnhub_client_factory = finnhub_client_factory
        self._default_resolution = default_resolution
        self._default_lookback_days = default_lookback_days
        self._batch_size = max(1, batch_size)

    def run(self) -> IngestionRetryResult:
        due_failures = self._failure_store.fetch_due_failures(limit=self._batch_size)
        attempted = 0
        retried_success = 0
        retried_no_data = 0
        retry_failed = 0
        dead_lettered = 0

        with self._finnhub_client_factory() as client:
            for failure in due_failures:
                attempted += 1
                outcome = self._retry_one_failure(failure, client)
                if outcome == "success":
                    retried_success += 1
                elif outcome == "no_data":
                    retried_no_data += 1
                elif outcome == "dead":
                    dead_lettered += 1
                else:
                    retry_failed += 1

        return IngestionRetryResult(
            due_failures=len(due_failures),
            attempted=attempted,
            retried_success=retried_success,
            retried_no_data=retried_no_data,
            retry_failed=retry_failed,
            dead_lettered=dead_lettered,
        )

    def _retry_one_failure(
        self,
        failure: IngestionFailureItem,
        client: FinnhubClient,
    ) -> str:
        if failure.job_name != "equity_ohlcv_ingestion":
            self._failure_store.mark_dead(failure.id, reason=f"unsupported_job:{failure.job_name}")
            return "dead"

        if not failure.asset_symbol:
            self._failure_store.mark_dead(failure.id, reason="missing_asset_symbol")
            return "dead"

        with self._session_factory() as session:
            asset = session.scalar(select(Asset).where(Asset.symbol == failure.asset_symbol))

        if asset is None:
            self._failure_store.mark_dead(
                failure.id,
                reason=f"asset_not_found:{failure.asset_symbol}",
            )
            return "dead"

        now_utc = datetime.now(UTC)
        resolution = str(failure.context.get("resolution", self._default_resolution))
        lookback_days = int(failure.context.get("lookback_days", self._default_lookback_days))
        from_unix = int(
            failure.context.get(
                "from_unix",
                int((now_utc - timedelta(days=lookback_days)).timestamp()),
            )
        )
        to_unix = int(failure.context.get("to_unix", int(now_utc.timestamp())))

        try:
            payload = client.get_stock_candles(
                failure.asset_symbol,
                resolution=resolution,
                from_unix=from_unix,
                to_unix=to_unix,
            )
            candles = normalize_finnhub_candles(payload)
        except Exception as exc:
            logger.exception(
                "ingestion_retry_failed",
                extra={
                    "failure_id": failure.id,
                    "job_name": failure.job_name,
                    "symbol": failure.asset_symbol,
                    "error": str(exc),
                },
            )
            dead = self._failure_store.register_retry_failure(
                failure.id,
                error_message=str(exc),
            )
            return "dead" if dead else "failed"

        if not candles:
            self._failure_store.mark_resolved(
                failure.id,
                resolution_context={"retry_result": "no_data"},
            )
            return "no_data"

        ingested_rows, skipped_rows = _persist_candles_for_asset(
            self._session_factory,
            asset_id=asset.id,
            source=failure.provider_name or "finnhub",
            ingest_id=uuid4().hex,
            candles=candles,
        )
        self._failure_store.mark_resolved(
            failure.id,
            resolution_context={
                "retry_result": "success",
                "retry_ingested_rows": ingested_rows,
                "retry_skipped_rows": skipped_rows,
            },
        )
        return "success"


def run_ingestion_failure_retry(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    audit_trail: JobAuditTrail | None = None,
    failure_store: IngestionFailureStore | None = None,
) -> IngestionRetryResult:
    """Run retry workflow for due ingestion failures."""

    resolved_settings = settings or get_settings()
    resolved_session_factory = session_factory or create_session_factory_from_settings(
        resolved_settings
    )
    resolved_audit = audit_trail or JobAuditTrail(resolved_session_factory)
    resolved_failure_store = failure_store or IngestionFailureStore(
        resolved_session_factory,
        max_attempts=resolved_settings.ingestion_failure_max_attempts,
        retry_backoff_minutes=resolved_settings.ingestion_failure_retry_backoff_minutes,
    )

    def _client_factory() -> FinnhubClient:
        return FinnhubClient.from_settings(resolved_settings)

    job = IngestionFailureRetryJob(
        resolved_session_factory,
        resolved_failure_store,
        _client_factory,
        default_resolution=resolved_settings.equity_ohlcv_resolution,
        default_lookback_days=resolved_settings.equity_ohlcv_lookback_days,
        batch_size=resolved_settings.ingestion_failure_retry_batch_size,
    )

    with resolved_audit.track_job_run(
        "ingestion_failure_retry",
        details={
            "batch_size": resolved_settings.ingestion_failure_retry_batch_size,
            "max_attempts": resolved_settings.ingestion_failure_max_attempts,
        },
    ) as run_handle:
        result = job.run()
        run_handle.add_details(
            {
                "due_failures": result.due_failures,
                "attempted": result.attempted,
                "retried_success": result.retried_success,
                "retried_no_data": result.retried_no_data,
                "retry_failed": result.retry_failed,
                "dead_lettered": result.dead_lettered,
            }
        )
        return result


def main() -> None:
    """CLI entrypoint for ingestion retry workflow."""

    result = run_ingestion_failure_retry()
    logger.info(
        "ingestion_failure_retry_completed",
        extra={
            "due_failures": result.due_failures,
            "attempted": result.attempted,
            "retried_success": result.retried_success,
            "retried_no_data": result.retried_no_data,
            "retry_failed": result.retry_failed,
            "dead_lettered": result.dead_lettered,
        },
    )
    print(
        "ingestion_failure_retry:"
        f" due_failures={result.due_failures}"
        f" attempted={result.attempted}"
        f" retried_success={result.retried_success}"
        f" retried_no_data={result.retried_no_data}"
        f" retry_failed={result.retry_failed}"
        f" dead_lettered={result.dead_lettered}"
    )


if __name__ == "__main__":
    main()
