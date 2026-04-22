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
- `PROVIDER_QUOTA_RESERVE_RATIO`: reserved quota fraction to avoid full depletion (default `0.1`)
- `ALPHA_VANTAGE_QUOTA_PER_MINUTE`: local quota guard for Alpha Vantage (default `5`)
- `FINNHUB_QUOTA_PER_MINUTE`: local quota guard for Finnhub (default `60`)

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
