# Environment Reference (Day 5)

Date: 22 April 2026
Scope: Home server deployment, swing mode, zero-budget-first

## Setup

1. Copy `.env.example` to `.env`.
2. Fill all required secrets.
3. Keep `.env` local only (never commit).

## Required Variables (MVP)

### Core and runtime
- `APP_NAME`: app identifier (`market-screener`)
- `APP_ENV`: `development` or `production`
- `TZ`: timezone (`Asia/Kolkata`)
- `LOG_LEVEL`: `INFO` by default
- `LOG_JSON`: `true` to emit structured JSON logs
- `API_HOST`, `API_PORT`: backend bind target
- `FRONTEND_HOST`, `FRONTEND_PORT`: frontend bind target

### Authentication
- `AUTH_ENABLED`: set `true` for basic auth
- `AUTH_BASIC_USERNAME`: dashboard username
- `AUTH_BASIC_PASSWORD`: dashboard password (strong)
- `APP_SECRET_KEY`: random long secret for signing/security logic

### Database and cache
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DATABASE_URL`: full PostgreSQL connection string
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`
- `REDIS_URL`: full Redis connection string

### Provider keys
- `FMP_API_KEY`: equities/fundamentals primary
- `FINNHUB_API_KEY`: equities/news backup
- `ALPHA_VANTAGE_API_KEY`: forex/commodities primary
- `MARKETAUX_API_KEY`: news primary
- `COINGECKO_API_KEY`: optional (empty allowed for public endpoints)
- `CCXT_EXCHANGE_ID`: default `binance`
- `CCXT_API_KEY`, `CCXT_API_SECRET`: optional unless private endpoints needed
- `WATCHLIST_SYMBOLS`: comma-separated symbol list for freshness monitoring (`AAPL,BTC,RELIANCE`); blank falls back to active-symbol sample
- `FRESHNESS_MONITOR_TARGET_AGE_MINUTES`: target freshness age for watchlist symbols before warning status (default `5`)
- `FRESHNESS_MONITOR_SYMBOL_LIMIT`: fallback active-symbol sample size when `WATCHLIST_SYMBOLS` is empty (default `20`)
- `PROVIDER_HEALTH_LOOKBACK_HOURS`: lookback window in hours for provider latency/success aggregation (default `24`)
- `PROVIDER_HEALTH_JOB_SAMPLE_LIMIT`: max recent job rows scanned per provider-health refresh run (default `500`)
- `PROVIDER_HEALTH_DASHBOARD_HISTORY_LIMIT`: max history points returned per provider in dashboard reads (default `24`)
- `INGESTION_STRESS_SYMBOL_LIMIT`: max active symbols included when running ingestion stress tests (default `100`)
- `INDICATOR_SNAPSHOT_SYMBOL_LIMIT`: max active symbols processed per indicator snapshot refresh run (default `150`)
- `INDICATOR_SNAPSHOT_PRICE_LOOKBACK_ROWS`: max recent OHLCV rows loaded per symbol for indicator calculations (default `260`)
- `INDICATOR_SNAPSHOT_SOURCE`: source tag persisted on `indicators_snapshot` rows (default `ta_v1`)
- `TREND_REGIME_SYMBOL_LIMIT`: max active symbols processed per trend-regime classification run (default `150`)
- `TREND_REGIME_INDICATOR_SOURCE`: indicator snapshot source filter used for trend-regime classification (default `ta_v1`)
- `TREND_REGIME_MACD_FLAT_TOLERANCE`: absolute MACD minus signal threshold used to classify range-bound regime (default `0.10`)
- `BREAKOUT_SYMBOL_LIMIT`: max active symbols processed per breakout detection run (default `150`)
- `BREAKOUT_LOOKBACK_BARS`: recent OHLCV bars loaded per symbol for breakout range baseline (default `20`)
- `BREAKOUT_BUFFER_RATIO`: minimum percentage break above/below recent range required to mark breakout (default `0.002`)
- `BREAKOUT_INDICATOR_SOURCE`: indicator snapshot source filter used for optional BB/ATR breakout context (default `ta_v1`)
- `RELATIVE_VOLUME_SYMBOL_LIMIT`: max active symbols processed per relative-volume run (default `150`)
- `RELATIVE_VOLUME_LOOKBACK_BARS`: recent OHLCV bars loaded per symbol for relative-volume baseline (default `20`)
- `RELATIVE_VOLUME_SPIKE_THRESHOLD`: relative-volume ratio threshold at/above which state is `spike` (default `1.5`)
- `RELATIVE_VOLUME_DRY_UP_THRESHOLD`: relative-volume ratio threshold at/below which state is `dry_up` (default `0.7`)
- `FUNDAMENTALS_SNAPSHOT_SYMBOL_LIMIT`: max active equity symbols processed per fundamentals snapshot pull run (default `150`)
- `FUNDAMENTALS_SNAPSHOT_PERIOD_TYPE`: reporting cadence for fundamentals pull (`annual` or `quarter`, default `annual`)
- `FUNDAMENTALS_SNAPSHOT_LIMIT_PER_SYMBOL`: max number of period rows fetched/written per symbol in each pull (default `2`)
- `FUNDAMENTALS_SNAPSHOT_SOURCE`: source tag persisted on `fundamentals_snapshot` rows (default `fmp_v1`)
- `EQUITY_OHLCV_RESOLUTION`: Finnhub candle resolution for equity ingestion (default `D`)
- `EQUITY_OHLCV_LOOKBACK_DAYS`: equity history backfill window in days (default `365`)
- `MARKET_HOLIDAYS_US`: comma-separated US market holidays (`YYYY-MM-DD`) used by trading calendar closure checks
- `MARKET_HOLIDAYS_NSE`: comma-separated NSE market holidays (`YYYY-MM-DD`) used by trading calendar closure checks
- `MARKET_HOLIDAYS_GLOBAL`: comma-separated global holidays (`YYYY-MM-DD`) for forex/commodity closure checks
- `CRYPTO_OHLCV_VS_CURRENCY`: CoinGecko quote currency for crypto OHLC pulls (default `usd`)
- `CRYPTO_OHLCV_DAYS`: CoinGecko OHLC lookback window in days (default `365`)
- `MACRO_OHLCV_LOOKBACK_DAYS`: forex/commodity backfill window in days for Alpha Vantage ingestion (default `365`)
- `MACRO_OHLCV_FOREX_OUTPUTSIZE`: Alpha Vantage FX output size (`compact` or `full`, default `full`)
- `MACRO_OHLCV_COMMODITY_INTERVAL`: Alpha Vantage commodity interval (default `daily`)
- `BACKFILL_VALIDATION_SYMBOL_LIMIT`: number of active equity symbols to validate per run (default `20`)
- `BACKFILL_VALIDATION_LOOKBACK_DAYS`: backfill validation window size in days (default `7`)
- `BACKFILL_VALIDATION_MIN_ROWS`: minimum rows expected per symbol inside validation window (default `3`)
- `BACKFILL_VALIDATION_MAX_LAST_ROW_AGE_DAYS`: max allowed age for latest row before stale failure (default `4`)
- `INGESTION_FAILURE_RETRY_BACKOFF_MINUTES`: retry delay schedule in minutes for ingestion failures (default `5,15,60`)
- `INGESTION_FAILURE_MAX_ATTEMPTS`: maximum attempts before a failure is dead-lettered (default `5`)
- `INGESTION_FAILURE_RETRY_BATCH_SIZE`: max due failures processed per retry run (default `50`)
- `PROVIDER_QUOTA_RESERVE_RATIO`: reserved quota fraction to avoid full depletion (default `0.1`)
- `FMP_QUOTA_PER_MINUTE`: local quota guard for FMP fundamentals requests (default `60`)
- `ALPHA_VANTAGE_QUOTA_PER_MINUTE`: local quota guard for Alpha Vantage (default `5`)
- `FINNHUB_QUOTA_PER_MINUTE`: local quota guard for Finnhub (default `60`)
- `COINGECKO_QUOTA_PER_MINUTE`: local quota guard for CoinGecko (default `30`)

### Alerting
- `ALERT_CHANNEL_TELEGRAM_ENABLED`: `true` by default
- `TELEGRAM_BOT_TOKEN`: Telegram bot token
- `TELEGRAM_CHAT_ID`: destination chat id
- `ALERT_MAX_PER_DAY`: locked at `5`
- `ALERT_COOLDOWN_MINUTES`: default `60`

## Optional Variables

- Email alert vars (`SMTP_*`) are optional in MVP.
- Fine-tuning vars for schedule, cache, and staleness can stay on defaults initially.

## Default Policy Alignment

These defaults match `docs/provider_matrix.md`:
- connect timeout 5s
- read timeout 12s
- total timeout 15s
- retries 3 with backoff `1,2,4`
- quota reserve ratio `0.1` with per-provider quota counters
- stale thresholds: price 15m, fundamentals 7d, news 24h

## Minimum Secrets Checklist Before First Run

- `APP_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `FMP_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `MARKETAUX_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `AUTH_BASIC_PASSWORD`

## Definition of Done (Day 5)

Day 5 is complete when:
- `.env.example` contains all required variables
- `docs/env_reference.md` explains usage and required fields
- `.env` is protected from commit via `.gitignore`
