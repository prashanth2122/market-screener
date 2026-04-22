# Implementation Spec (Elite Personal Product)

## 1. Purpose

This document defines exactly what to build for a high-quality personal market screener and how to validate that it works.

## 2. Scope

### In Scope (v1)
- Multi-asset screening: stocks, crypto, indices, commodities, forex
- Data ingestion from at least two providers per major asset class
- Technical indicators and trend regime detection
- Fundamental quality scoring (for equities where data is available)
- News sentiment and event risk tagging
- Composite score with explainable factor breakdown
- Dashboard with ranking, watchlist, chart, and alert history
- Alerts via email and one chat channel (Telegram or Slack)

### Out of Scope (v1)
- Automated trading execution
- Options chain analytics
- Fully automated ML model retraining pipeline

## 3. System Requirements

### Functional Requirements
- Fetch and store OHLCV data for tracked symbols.
- Compute indicators on scheduled intervals.
- Compute score per symbol and persist score history.
- Trigger alerts based on configurable rules.
- Expose API endpoints for screener and drill-down views.
- Render dashboard with filters and sorting.

### Non-Functional Requirements
- Data freshness target: <= 5 minutes for active watchlist symbols.
- Job reliability target: >= 99% successful scheduled runs over rolling 7 days.
- P95 API latency target for dashboard reads: <= 400 ms (local network).
- Alert delay target from signal to delivery: <= 90 seconds.

## 4. Logical Architecture

- `collector` service: provider adapters, retries, quota handling
- `normalizer` service: map provider payloads to unified schema
- `compute` service: indicators, fundamentals, sentiment, scoring
- `alert` service: rule evaluation and notification dispatch
- `api` service: query endpoints for UI
- `ui` application: dashboards and settings

## 5. Data Contracts

### Core Tables
- `assets`: symbol, asset_type, exchange, base_currency, quote_currency, active
- `prices`: asset_id, ts, open, high, low, close, volume, source, ingest_id
- `fundamentals_snapshot`: asset_id, ts, pe, pb, debt_to_equity, roa, roe, eps_growth, revenue_growth
- `indicators_snapshot`: asset_id, ts, rsi14, macd, macd_signal, ma50, ma200, atr14, bb_upper, bb_lower
- `news_events`: asset_id, ts, source, headline, url, sentiment_score, event_type, risk_flag
- `scores`: asset_id, ts, model_version, technical_score, fundamental_score, sentiment_score, total_score, signal
- `alerts`: asset_id, ts, rule_id, channel, status, payload
- `provider_health`: provider_name, ts, latency_ms, success_rate, quota_remaining

### Key Rules
- Every row includes `source` and ingestion timestamp for auditability.
- Score rows are immutable and version-tagged.
- Upserts allowed for late-arriving market data only by `(asset_id, ts, source)` key.

## 6. Scoring Design (v1)

`total_score = 0.45 * technical + 0.35 * fundamental + 0.20 * sentiment`

### Technical Subscore Inputs
- Trend: price vs MA200
- Momentum: RSI14 and MACD state
- Strength: distance to 52-week high and breakout confirmation
- Volume confirmation: relative volume vs 20-day average

### Fundamental Subscore Inputs
- Piotroski F-score normalized to 0-100
- Altman Z-score bucket mapping
- Growth + quality metrics (EPS and revenue growth, ROE, debt discipline)

### Sentiment Subscore Inputs
- Weighted sentiment of last 72h
- Event-risk penalties (earnings miss, litigation, fraud, regulatory actions)

### Signal Mapping
- `Strong Buy`: total_score >= 80 and no hard-risk flag
- `Buy`: 70-79
- `Watch`: 60-69
- `Avoid`: <60 or hard-risk flag

## 7. API Surface (v1)

- `GET /health`
- `GET /assets?type=&search=&active=`
- `GET /screener?asset_type=&min_score=&signal=&sort=`
- `GET /assets/{symbol}/overview`
- `GET /assets/{symbol}/prices?range=`
- `GET /assets/{symbol}/indicators?range=`
- `GET /assets/{symbol}/news?range=`
- `GET /alerts?status=&range=`
- `POST /watchlist`
- `DELETE /watchlist/{symbol}`
- `POST /alerts/test`

## 8. Dashboard Requirements

### Main Screener Page
- Sortable table: symbol, price, score, signal, 24h change, distance to ATH, trend state
- Filters: asset class, exchange, score band, sentiment band, volume spike
- Signal explanation popover with factor contributions

### Symbol Detail Page
- Price chart with MA50 and MA200 overlays
- Indicator panel (RSI, MACD, ATR, BB)
- Fundamentals panel (latest snapshot + trend)
- News panel with risk tags and sentiment trend
- Alert history and active rule view

## 9. Alerting Requirements

- Minimum rule templates:
  - breakout with volume confirmation
  - discounted buy candidate
  - score upgrade/downgrade threshold cross
  - negative sentiment shock
- Channels: email + one chat integration
- Cooldown support to reduce alert spam
- Daily summary digest at end of trading day (region-aware)

## 10. Observability

- Structured logs with correlation IDs (`ingest_id`, `job_id`).
- Metrics:
  - job success/failure
  - provider latency and quota headroom
  - API latency and error rates
  - alert trigger count and delivery success
- Basic dashboard via Grafana or lightweight equivalent.

## 11. Testing Strategy

- Unit tests:
  - indicator calculations
  - score function and signal threshold mapping
  - alert rule evaluation
- Integration tests:
  - provider adapter normalization
  - end-to-end ingestion to score persistence
- Regression tests:
  - fixed historical dataset snapshots for deterministic score checks

## 12. Definition of Done (v1)

A release is done only if:
- all critical jobs run for 7 consecutive days without manual restart
- data freshness SLA is met for watchlist symbols
- alert precision is acceptable for personal workflow (manual evaluation log)
- dashboard supports complete decision loop without external spreadsheets

## 13. Execution Link

Follow the day-by-day sequence in [`100_DAY_PLAN.md`](100_DAY_PLAN.md).

## 14. Acceptance Checklist (Day 8)

Use this checklist as the objective pass/fail gate for MVP readiness.

### A. Data Freshness

| ID | Requirement | How to Measure | Pass Criteria | Evidence |
|---|---|---|---|---|
| A1 | Active watchlist price freshness | Compare `now_utc - latest_price_ts` per active symbol | 95% of active symbols <= 5 minutes; 100% <= 15 minutes | Freshness report snapshot |
| A2 | Fundamentals freshness | Compare `now_utc - fundamentals_ts` | 100% of equities with fundamentals <= 7 days | DB query output |
| A3 | News freshness for scoring | Compare `now_utc - latest_news_ts` | 95% of symbols <= 24 hours | News coverage report |

### B. Ingestion Reliability

| ID | Requirement | How to Measure | Pass Criteria | Evidence |
|---|---|---|---|---|
| B1 | Scheduled job success | Rolling 7-day success rate of critical jobs | >= 99% success for ingestion, compute, and score jobs | Job metrics dashboard |
| B2 | Provider failover behavior | Simulate primary provider timeout/429 | Backup provider used within same cycle, no crash | Test run logs |
| B3 | Idempotent re-run safety | Re-run same ingestion window | No duplicate rows beyond upsert key rules | Row count diff report |

### C. Alert Timeliness and Quality

| ID | Requirement | How to Measure | Pass Criteria | Evidence |
|---|---|---|---|---|
| C1 | Signal-to-Telegram latency | `alert_sent_ts - signal_created_ts` | p95 <= 90 seconds | Alert latency query |
| C2 | Daily alert cap enforcement | Count actionable alerts/day | <= 5/day always | Alert summary report |
| C3 | Cooldown and duplicate suppression | Trigger repeated same-condition signal | No duplicate actionable alert within cooldown | Alert event logs |
| C4 | Negative-news override | Inject negative high-risk news on strong technical setup | `Strong Buy` blocked as expected | Test case output |

### D. Scoring and Guardrails

| ID | Requirement | How to Measure | Pass Criteria | Evidence |
|---|---|---|---|---|
| D1 | Score range validity | Check all generated scores | Scores always between 0 and 100 | Validation query |
| D2 | Signal mapping consistency | Validate threshold mapping against test fixtures | 100% fixture pass | Unit test results |
| D3 | Hard buy-block rules | Evaluate assets failing MA200/liquidity/high-risk-news | Must not emit `Strong Buy` | Rule engine tests |

### E. Dashboard Utility

| ID | Requirement | How to Measure | Pass Criteria | Evidence |
|---|---|---|---|---|
| E1 | Screener usability | Verify sorting/filtering on score/signal/segment | All primary filters and sort paths work | Manual QA checklist |
| E2 | Symbol detail completeness | Open detail page for equity + crypto symbols | Chart, indicators, news, score explanation all render | QA screenshots |
| E3 | Read performance | Measure API response latency under local load | p95 <= 400 ms for screener reads | API perf report |
| E4 | End-to-end decision loop | Run daily workflow from discovery to alert review | Complete without external spreadsheet dependency | Owner sign-off note |

### F. Security and Config Baseline

| ID | Requirement | How to Measure | Pass Criteria | Evidence |
|---|---|---|---|---|
| F1 | Secret hygiene | Verify git tracking and file patterns | `.env` never tracked; `.env.example` present | Git check output |
| F2 | Basic auth enforcement | Attempt dashboard access unauthenticated | Access denied without valid credentials | QA test result |
| F3 | Config portability | Bootstrap on clean machine using docs | Service starts with `.env.example` + docs guidance | Setup run log |

### G. Operational Readiness

| ID | Requirement | How to Measure | Pass Criteria | Evidence |
|---|---|---|---|---|
| G1 | Daily health checks | Run start-of-day checklist for 5 consecutive days | No blocker unresolved across 5 days | Runbook checklist records |
| G2 | Backup verification | Execute backup and restore smoke test | Restore succeeds for latest snapshot | Restore test output |
| G3 | Incident response readiness | Simulate provider outage and Telegram failure | System degrades gracefully and recovers | Incident drill notes |

## 15. Day 8 Completion Rule

Day 8 is complete when:
- every acceptance item has a measurable method
- every acceptance item has a numeric or binary pass criterion
- required evidence artifacts are defined for release review
