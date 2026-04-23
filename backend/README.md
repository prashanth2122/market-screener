# Backend Module

Purpose:
- Data ingestion, normalization, scoring, alerting, and API services.

Directory layout:
- `src/market_screener/` application package
- `tests/` unit and integration tests
- `migrations/` database schema migrations

Stack baseline:
- Python 3.12+
- FastAPI
- PostgreSQL (planned integration)
- Redis (planned integration)

## Quickstart

From repo root:

```powershell
python -m pip install -e .\backend[dev]
python -m uvicorn market_screener.main:app --app-dir .\backend\src --reload --port 8000
```

Run tests:

```powershell
python -m pytest .\backend\tests
```

Migration commands:

```powershell
python -m alembic -c .\backend\alembic.ini upgrade head
python -m alembic -c .\backend\alembic.ini revision -m "describe_change"
```

Configuration management:

- Runtime settings module: `backend/src/market_screener/core/settings.py`
- Settings reload helper (useful for tests): `reload_settings()`
- Safe debug dump with redacted secrets: `as_safe_dict()`

Structured logging:

- JSON log formatter with request correlation IDs
- HTTP middleware emits `request_started` and `request_completed` events
- Response header includes `X-Request-ID`

Health checks:

- `GET /health` for load-balancer and runtime readiness checks
- `GET /api/v1/system/health` for namespaced system diagnostics
- Returns `200` when PostgreSQL and Redis checks are up, otherwise `503`

Provider clients:

- Alpha Vantage wrapper: `backend/src/market_screener/providers/alpha_vantage.py`
- Finnhub wrapper: `backend/src/market_screener/providers/finnhub.py`
- CoinGecko wrapper: `backend/src/market_screener/providers/coingecko.py`
- FMP fundamentals wrapper: `backend/src/market_screener/providers/fmp.py`
- Marketaux news wrapper: `backend/src/market_screener/providers/marketaux.py`
- Typed provider exceptions: `backend/src/market_screener/providers/exceptions.py`
- Shared retry policy: `backend/src/market_screener/providers/retry.py`
- Token-bucket rate-limit guard: `backend/src/market_screener/providers/rate_limit.py`

Ingestion jobs:

- Symbol metadata ingestion: `python -m market_screener.jobs.symbol_metadata`
- Job source: `backend/src/market_screener/jobs/symbol_metadata.py`
- Equity OHLCV ingestion: `python -m market_screener.jobs.equity_ohlcv`
- Job source: `backend/src/market_screener/jobs/equity_ohlcv.py`
- Crypto OHLCV ingestion: `python -m market_screener.jobs.crypto_ohlcv`
- Job source: `backend/src/market_screener/jobs/crypto_ohlcv.py`
- Forex/commodity OHLCV ingestion: `python -m market_screener.jobs.macro_ohlcv`
- Job source: `backend/src/market_screener/jobs/macro_ohlcv.py`
- Equity backfill validation: `python -m market_screener.jobs.backfill_validation`
- Validation source: `backend/src/market_screener/jobs/backfill_validation.py`
- Watchlist freshness monitor: `python -m market_screener.jobs.freshness_monitor`
- Monitor source: `backend/src/market_screener/jobs/freshness_monitor.py`
- Provider health dashboard refresh: `python -m market_screener.jobs.provider_health_dashboard`
- Dashboard source: `backend/src/market_screener/jobs/provider_health_dashboard.py`
- Ingestion stress test: `python -m market_screener.jobs.ingestion_stress`
- Stress source: `backend/src/market_screener/jobs/ingestion_stress.py`
- Ingestion failure retry workflow: `python -m market_screener.jobs.ingestion_retry`
- Retry source: `backend/src/market_screener/jobs/ingestion_retry.py`
- Indicator snapshot refresh: `python -m market_screener.jobs.indicator_snapshot`
- Indicator snapshot source: `backend/src/market_screener/jobs/indicator_snapshot.py`
- Fundamentals snapshot pull: `python -m market_screener.jobs.fundamentals_snapshot`
- Fundamentals snapshot source: `backend/src/market_screener/jobs/fundamentals_snapshot.py`
- Fundamentals snapshot schema: `backend/src/market_screener/db/models/core.py` (`fundamentals_snapshot` table for annual/quarterly fundamentals ingestion)
- News ingestion pull: `python -m market_screener.jobs.news_ingestion`
- News ingestion source: `backend/src/market_screener/jobs/news_ingestion.py`
- News article schema: `backend/src/market_screener/db/models/core.py` (`news_events` table for article storage feeding sentiment/risk pipelines)
- Score history schema: `backend/src/market_screener/db/models/core.py` (`score_history` table for per-asset score snapshots by model version)
- Signal history schema: `backend/src/market_screener/db/models/core.py` (`signal_history` table for per-asset signal state and rationale snapshots)
- Sentiment scoring pipeline: `python -m market_screener.jobs.sentiment_scoring`
- Sentiment scoring source: `backend/src/market_screener/jobs/sentiment_scoring.py`
- Event-risk tagging pipeline: `python -m market_screener.jobs.event_risk_tagging`
- Event-risk tagging source: `backend/src/market_screener/jobs/event_risk_tagging.py`
- Email alert dispatch: `python -m market_screener.jobs.email_alert_dispatch`
- Email alert dispatch source: `backend/src/market_screener/jobs/email_alert_dispatch.py`
- Score/signal 90-day backfill: `python -m market_screener.jobs.score_signal_backfill`
- Score/signal backfill source: `backend/src/market_screener/jobs/score_signal_backfill.py`
- Trend regime classification: `python -m market_screener.jobs.trend_regime`
- Trend regime source: `backend/src/market_screener/jobs/trend_regime.py`
- Breakout detection: `python -m market_screener.jobs.breakout_detection`
- Breakout source: `backend/src/market_screener/jobs/breakout_detection.py`
- Relative volume calculation: `python -m market_screener.jobs.relative_volume`
- Relative volume source: `backend/src/market_screener/jobs/relative_volume.py`
- Ingestion audit trail helper: `backend/src/market_screener/jobs/audit.py` (writes to `jobs` table)
- Idempotency key helper: `backend/src/market_screener/jobs/idempotency.py` (deterministic repeated-pull guard keys)
- Ingestion failure store: `backend/src/market_screener/jobs/ingestion_failures.py` (writes to `ingestion_failures` table)
- Shared price normalization schema: `backend/src/market_screener/jobs/price_normalization.py`
- Ingestion adapter interfaces: `backend/src/market_screener/jobs/ingestion_adapters.py` (provider-specific fetch/normalize boundaries)
- UTC timezone normalization helper: `backend/src/market_screener/core/timezone.py` (normalizes persisted datetimes to UTC)
- Trading calendar helper: `backend/src/market_screener/core/trading_calendar.py` (weekend + holiday market closure checks)
- TA library integration helper: `backend/src/market_screener/core/ta_library.py` (TA backend availability + indicator wrappers)
- Indicator calculations helper: `backend/src/market_screener/core/indicators.py` (MA50, MA200, RSI14, MACD, ATR14, and Bollinger band series + latest snapshots)
- Indicator reference validation helper: `backend/src/market_screener/core/indicator_reference_validation.py` (validates indicator outputs against versioned checkpoint references)
- Piotroski F-score helper: `backend/src/market_screener/core/piotroski.py` (9-point fundamentals quality scoring from current vs prior period)
- Altman Z-score helper: `backend/src/market_screener/core/altman.py` (financial-distress zone scoring from fundamentals ratios)
- Growth metrics helper: `backend/src/market_screener/core/growth_metrics.py` (EPS and revenue growth calculations from current vs prior period)
- Fundamentals quality normalization helper: `backend/src/market_screener/core/fundamentals_quality.py` (combines Piotroski, Altman, growth, ROE, and debt discipline into 0-100)
- Sentiment scoring helper: `backend/src/market_screener/core/sentiment.py` (article-level sentiment derivation + 72h weighted sentiment aggregation)
- Event-risk tagging helper: `backend/src/market_screener/core/event_risk.py` (rule-based event-type and risk-flag tagging from article content and sentiment)
- Score factor transform helper: `backend/src/market_screener/core/score_factors.py` (model version, component weights, and technical/fundamental/sentiment factor transforms)
- Composite score engine helper: `backend/src/market_screener/core/composite_score.py` (v1 weighted score assembly with component reweighting and contribution diagnostics)
- Score explanation helper: `backend/src/market_screener/core/score_explanation.py` (per-asset explanation payload with summary, component breakdown, drivers, risk context, and gaps)
- Signal mapping helper: `backend/src/market_screener/core/signal_mapping.py` (Strong Buy / Buy / Watch / Avoid rules with risk overrides and confidence/data-coverage downgrades)
- SMTP email alert channel: `backend/src/market_screener/alerts/email_channel.py` (digest rendering + SMTP delivery integration for actionable signals)
- Combined sentiment+risk integration tests: `backend/tests/test_sentiment_event_risk_pipeline.py` (validates sentiment backfill and downstream event-risk tagging behavior)
- Trend regime helper: `backend/src/market_screener/core/trend_regime.py` (bull/bear/range and transition regime classification)
- Breakout helper: `backend/src/market_screener/core/breakout.py` (recent-range breakout and breakdown detection)
- Relative volume helper: `backend/src/market_screener/core/relative_volume.py` (current volume vs trailing baseline ratio classification)

System dashboard endpoints:

- `GET /api/v1/system/provider-health` for provider latency/success dashboard reads.
- `POST /api/v1/system/provider-health/refresh` to recompute provider dashboard snapshots from recent job history.
