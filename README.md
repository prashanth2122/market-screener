# Market Screener (Elite Personal Build)

Personal-use multi-asset screener for stocks, crypto, indices, commodities, and forex with:
- live and end-of-day data ingestion
- technical + fundamental + sentiment scoring
- ranking, watchlists, and actionable alerts
- disciplined engineering quality (tests, observability, recoverability)

This repository now acts as the execution center for the build.

## 1) Product Goal

Build a high-signal decision assistant for your own investing workflow:
- find discounted but strong assets
- detect momentum breakouts with volume confirmation
- avoid low-quality setups with weak fundamentals or negative news flow
- receive alerts only when rules are truly meaningful

## 2) What "Elite Level" Means For This Project

- Reliable data: every data point has source, timestamp, and quality flags.
- Reproducible signals: indicator and score calculations are versioned.
- Low operational drag: automated jobs, retries, caching, and clear logs.
- Measurable quality: test coverage on critical paths, alert precision tracking.
- Fast decision UX: one dashboard view shows ranking, context, and risk.

## 3) Initial Architecture (Personal-Scale, Production-Grade Habits)

### Core Services
- `ingestion`: API clients + scheduler + rate-limit aware fetching
- `analytics`: technical indicators, fundamentals model, sentiment model
- `scoring`: weighted score engine and signal rules
- `alerts`: rule engine + notification delivery (email/Telegram/Slack)
- `api`: query layer for dashboard and mobile usage
- `ui`: dashboard for watchlist, ranking, charts, and event drill-down

### Data Flow
1. Fetch market and news data from multiple providers.
2. Normalize and store raw records with provenance metadata.
3. Run indicator and fundamentals computation jobs.
4. Aggregate into per-asset feature vectors.
5. Compute score and generate signals.
6. Expose to UI and alert engine.

### Recommended Stack (Pragmatic)
- Backend: Python 3.12 + FastAPI
- Job orchestration: APScheduler or Celery + Redis
- Database: PostgreSQL (plus TimescaleDB extension optional)
- Cache: Redis
- Frontend: Next.js + TypeScript
- Charts: Lightweight Charts or Plotly
- Infra (local first): Docker Compose
- CI: GitHub Actions

## 4) Data Provider Strategy

Use multi-source ingestion with fallback order:
- Stocks/indices/fundamentals: Alpha Vantage, Finnhub, FinancialModelingPrep
- Crypto: CoinGecko (primary), exchange APIs via CCXT (secondary)
- Commodities/forex: Alpha Vantage + FMP
- News/sentiment: Marketaux + Finnhub/FMP news endpoints

Provider selection rules:
- always track quota usage
- fail over to backup provider when quota/latency fails
- cache frequently requested symbols
- preserve raw API payload snapshots for debugging

## 5) Scoring Model (v1 Baseline)

Composite score from 0-100:
- Technical strength: 45%
- Fundamental quality: 35%
- News/sentiment and event risk: 20%

Example signal gates:
- `Strong Buy`: score >= 80, trend up, no red-flag news in last 72h
- `Watch`: score 65-79 with improving momentum
- `Avoid`: high downside risk (weak trend + poor fundamentals + negative events)

All formulas should be versioned (for example `score_model_version=v1.0.0`) so changes stay auditable.

## 6) Quality Standards

- Unit tests for indicator math, scoring logic, and rule engine
- Integration tests for ingestion and provider fallback
- Idempotent jobs (safe re-runs)
- Dead-letter handling for failed ingestion payloads
- Structured logs and dashboards for error rate, job delay, alert count

## 7) Security and Privacy (Personal Product)

- Keep API keys and SMTP credentials in `.env` only
- Never commit secrets
- Encrypt backups
- Add optional local auth for dashboard access
- Maintain a simple audit trail for triggered alerts

## 8) Execution Docs

- Elite implementation specification: [`docs/IMPLEMENTATION_SPEC.md`](docs/IMPLEMENTATION_SPEC.md)
- 100-day execution plan: [`docs/100_DAY_PLAN.md`](docs/100_DAY_PLAN.md)
- Owner decision tracker: [`docs/OWNER_QUESTIONS.md`](docs/OWNER_QUESTIONS.md)
- Provider matrix: [`docs/provider_matrix.md`](docs/provider_matrix.md)
- Day 1 success brief: [`docs/DAY_01_SUCCESS_BRIEF.md`](docs/DAY_01_SUCCESS_BRIEF.md)
- Execution log: [`docs/EXECUTION_LOG.md`](docs/EXECUTION_LOG.md)
- Repository structure: [`docs/REPO_STRUCTURE.md`](docs/REPO_STRUCTURE.md)
- Environment reference: [`docs/env_reference.md`](docs/env_reference.md)
- Architecture and flow: [`docs/ARCHITECTURE_DATA_FLOW.md`](docs/ARCHITECTURE_DATA_FLOW.md)
- Scope matrix: [`docs/scope_matrix.md`](docs/scope_matrix.md)
- Engineering standards: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Pre-commit hooks config: [`.pre-commit-config.yaml`](.pre-commit-config.yaml)
- Docker stack guide: [`infra/docker/README.md`](infra/docker/README.md)
- Backend migration guide: [`backend/migrations/README.md`](backend/migrations/README.md)

## 9) Immediate Next Build Steps

1. Finalize scope for MVP symbols and markets.
2. Scaffold backend + DB schema + ingestion framework.
3. Implement first score pipeline (technical-only), then fundamentals/news.
4. Build dashboard v1 and alert delivery.
5. Start paper-trading style validation loop on your signals.
