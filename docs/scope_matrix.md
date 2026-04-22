# Scope Matrix (Day 7)

Date: 22 April 2026
Owner: Prash
Profile: Personal swing screener, home server, free-tier-first

## 1) Scope Buckets

- `MUST (MVP)`: required for a usable daily decision workflow.
- `SHOULD (v1+)`: high value but not required for first stable daily use.
- `LATER`: explicitly deferred to protect delivery speed.

## 2) MUST (MVP)

### Data and Ingestion
- Ingest 150 locked symbols (`S&P50 + NSE50 + Crypto50`).
- Provider fallback enabled per Day 3 matrix.
- Rate-limit aware fetching with retries and timeout policy.
- Normalized storage for prices, fundamentals (where available), and news.

### Analytics and Scoring
- Core indicators: MA50, MA200, RSI14, MACD, ATR, Bollinger Bands.
- Fundamental metrics: Piotroski F-score, Altman Z, EPS growth, debt/equity, ROE.
- Sentiment pipeline with negative-news override.
- Composite score (0-100) with explainable factor breakdown.
- Signal classes: `Strong Buy`, `Buy`, `Watch`, `Avoid`.

### Alerting
- Telegram alerts only (primary channel).
- Alert cap: max 5 actionable alerts/day.
- Cooldown and duplicate suppression.
- Hard buy-block guardrails:
- high-risk negative news
- price below MA200
- very low liquidity

### Product Surface
- Basic-auth protected dashboard.
- Screener table with filters and sorting.
- Symbol detail with chart + indicators + fundamentals + news + signal explanation.
- Alert history view.

### Platform and Operations
- Runs on home server.
- PostgreSQL + Redis baseline.
- Basic health checks and structured logs.
- `.env`-driven configuration with `.env.example`.

## 3) SHOULD (v1+)

- Email alerts as secondary channel.
- Daily summary digest.
- Provider health dashboard (lightweight monitoring view).
- Replay command for missed ingestion windows.
- Better cache policy tuning by market session.
- UI watchlist presets and saved filters.
- Score explanation improvements (factor trend over time).

## 4) LATER (Deferred)

- Auto trade execution / broker integration.
- Options-chain analytics and options greeks.
- Full machine-learning model training/retraining pipeline.
- Multi-user auth and role management.
- Mobile app and push notifications.
- Paid data dependencies as default path.

## 5) Out-of-Scope Rules (Hard)

- No feature enters MVP if it adds paid dependency requirements.
- No feature enters MVP if it delays reliable daily use.
- No feature enters MVP if it requires non-trivial maintenance overhead on home server.

## 6) Fast Decision Framework for New Requests

Evaluate any new feature with this order:
1. Does it improve daily decision quality immediately?
2. Does it preserve zero-budget-first operation?
3. Can it be delivered in <= 2 focused days without destabilizing core flows?
4. Does it avoid expanding operational burden significantly?

Decision:
- If all are yes -> `MUST` candidate.
- If value is high but not immediate -> `SHOULD`.
- If costly/complex/non-core -> `LATER`.

## 7) Acceptance Gate for Moving from SHOULD to MUST

A `SHOULD` item can move to `MUST` only when:
- current MVP reliability targets are met for 7 consecutive days
- alert precision is acceptable in your validation journal
- change has clear measurable benefit to decision quality

## 8) Day 7 Definition of Done

Day 7 is complete when:
- MVP boundaries are explicit and frozen
- v1+ and deferred work are clearly separated
- new feature requests can be triaged in minutes
