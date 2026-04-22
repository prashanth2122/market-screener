# Provider Matrix (Day 3)

Date: 22 April 2026
Owner: Prash
Scope: MVP (150 symbols, swing timeframe, free-tier-first)

## 1) Provider Order (Locked)

### Equities (US + NSE)
- Primary: `FinancialModelingPrep (FMP)`
- Backup: `Finnhub`
- Last-resort fallback for gap-fill only: `yfinance` (unofficial, non-critical use)

### Crypto
- Primary: `CoinGecko`
- Backup: `CCXT` (exchange endpoints)

### Forex and Commodities
- Primary: `Alpha Vantage`
- Backup: `FMP`

### News/Sentiment
- Primary: `Marketaux`
- Backup: `Finnhub` news endpoints

## 2) Request Policy (Default)

- Connect timeout: `5s`
- Read timeout: `12s`
- Total request timeout: `15s`
- Retry attempts: `3`
- Retry backoff: exponential (`1s`, `2s`, `4s`) with small jitter
- Retry only on: timeout, `429`, and `5xx`
- Do not retry on: `4xx` (except `429`)

## 3) Failover Rules

1. Try primary provider.
2. If request fails by retry policy or quota exhaustion, switch to backup.
3. Mark provider health event with reason (`timeout`, `rate_limit`, `server_error`, `schema_error`).
4. If both providers fail:
- use last known cached value when data age is within allowed staleness window
- otherwise mark symbol as `data_unavailable` for that run

## 4) Caching and Staleness Windows

- Intraday price cache TTL (swing mode): `60s`
- Daily/fundamental cache TTL: `24h`
- News cache TTL: `15m`
- Max acceptable stale data for scoring:
- prices: `<= 15m`
- fundamentals: `<= 7d`
- news sentiment: `<= 24h`

If stale threshold is breached, asset can still render in UI but cannot receive `Strong Buy`.

## 5) Quota and Rate-Limit Handling

- Track per-provider counters: requests, failures, `429` count, moving latency.
- Use token-bucket limiter per provider key.
- Reserve 10% quota buffer for:
- manual refresh
- retries
- alert-critical rechecks
- When remaining quota drops below 15%, reduce non-critical polling frequency.

## 6) Normalization Contract

All provider adapters must output normalized records:
- `symbol`
- `asset_type`
- `timestamp_utc`
- `open`, `high`, `low`, `close`, `volume` (where applicable)
- `source_provider`
- `source_latency_ms`
- `ingest_id`
- `quality_flag` (`ok`, `stale`, `partial`, `error`)

News adapters must also output:
- `headline`
- `url`
- `published_at_utc`
- `sentiment_score` (if provider gives one)
- `event_risk_tag` (derived downstream if not provided)

## 7) Provider Health States

- `healthy`: success rate >= 98% over rolling window
- `degraded`: success rate 90-97% or elevated latency
- `unhealthy`: success rate < 90% or repeated quota/rate-limit failures

Routing behavior:
- `healthy`: normal primary-first routing
- `degraded`: lower concurrency to provider and pre-warm backup
- `unhealthy`: route traffic to backup by default for current cycle

## 8) Daily Operational Checks

- Verify provider health summary at start of day.
- Verify backup provider path with at least one test symbol per segment.
- Verify quota headroom before market open windows.

## 9) Definition of Done (Day 3)

Day 3 is complete when:
- provider order is fixed for all asset classes
- failover behavior is deterministic
- timeout/retry policy is explicit
- adapter normalization contract is frozen for implementation
