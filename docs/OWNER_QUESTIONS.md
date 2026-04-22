# Owner Questions (Decision Log)

Purpose: Capture open decisions required to execute this project without ambiguity.

How to use:
- Add your answer under each question.
- Change status from `Pending` to `Answered`.
- Keep this file updated as new decisions appear.

## Q1. Priority Market Scope
- Status: `Answered`
- Question: Which market should be your Day-1 priority?
- Options: India equities, US equities, crypto, mixed.
- Why this matters: Drives provider setup, trading hours logic, and initial symbol universe.
- Your answer: Mixed.

## Q2. Initial Symbol Universe
- Status: `Answered`
- Question: How many symbols should MVP track initially, and which exact symbols?
- Suggested range: 20-50 symbols for first stable release.
- Why this matters: Controls rate-limit pressure and data freshness targets.
- Your answer: Mixed universe, top 50 from each major segment, confirmed. MVP set to S&P 500 top 50 + NSE top 50 + Crypto top 50 (150 symbols total).

## Q3. Data Provider Preference
- Status: `Answered`
- Question: Which providers do you want as primary vs backup per asset class?
- Why this matters: We need deterministic failover order before writing adapters.
- Your answer: Use the suggested default provider order. Equities: FMP -> Finnhub. Crypto: CoinGecko -> CCXT. Forex/Commodities: Alpha Vantage -> FMP. News: Marketaux -> Finnhub.

## Q4. Timeframe Strategy
- Status: `Answered`
- Question: Which timeframes matter most for your decisions?
- Options: 1m/5m intraday, hourly, daily swing, mixed.
- Why this matters: Defines ingestion intervals and indicator windows.
- Your answer: Swing timeframe.

## Q5. Decision Style
- Status: `Answered`
- Question: Is this screener mainly for swing trades, long-term investing, or both?
- Why this matters: Affects score weighting, alert logic, and UI defaults.
- Your answer: Swing style, minimum holding horizon around one month.

## Q6. Alert Channels
- Status: `Answered`
- Question: Where do you want alerts first?
- Options: Email only, Telegram, Slack, combinations.
- Why this matters: Determines first notification integration scope.
- Your answer: Telegram first.

## Q7. Alert Noise Tolerance
- Status: `Answered`
- Question: How many actionable alerts per day are acceptable?
- Suggested baseline: 3-10 high-confidence alerts/day.
- Why this matters: Needed for threshold and cooldown tuning.
- Your answer: Maximum 5 actionable Telegram alerts per day.

## Q8. Risk Guardrails
- Status: `Answered`
- Question: What hard filters should always block a buy signal?
- Examples: Negative event flag, weak trend, low liquidity, poor fundamental score.
- Why this matters: Prevents obvious low-quality signals.
- Your answer: Use default hard buy-block filters: negative high-risk news flag, price below MA200 trend filter, and very low liquidity condition.

## Q9. Fundamental Metrics Priority
- Status: `Answered`
- Question: Which fundamental factors are mandatory for you?
- Options: F-score, Altman Z, EPS growth, debt/equity, ROE, others.
- Why this matters: Locks data model and score inputs.
- Your answer: Use default mandatory fundamentals: Piotroski F-score, Altman Z-score, EPS growth, debt/equity, and ROE.

## Q10. News/Sentiment Sensitivity
- Status: `Answered`
- Question: Should negative news override technical strength by default?
- Why this matters: Defines event-risk penalty behavior.
- Your answer: Yes. Negative news should override technical strength by default.

## Q11. Deployment Preference
- Status: `Answered`
- Question: Where will this run initially?
- Options: Local machine only, home server, cloud VM, managed platform.
- Why this matters: Affects infra choices, observability, and backup setup.
- Your answer: Home server.

## Q12. Budget Constraints
- Status: `Answered`
- Question: What is your monthly budget cap for APIs and hosting?
- Why this matters: Determines free-tier-only design vs paid reliability upgrades.
- Your answer: Mostly zero budget (free-tier-first design).

## Q13. Authentication Requirement
- Status: `Answered`
- Question: Do you need login now for personal use, or can we delay auth to post-MVP?
- Why this matters: Can remove unnecessary complexity in first 30 days.
- Your answer: Basic auth required.

## Q14. Validation Method
- Status: `Answered`
- Question: How do you want to validate score quality?
- Options: Paper-trading journal, weekly manual review, historical replay, all.
- Why this matters: Needed to establish feedback loop and model iteration process.
- Your answer: Mixed validation (paper journal + manual review + historical replay).

## Q15. Definition of Success at Day 100
- Status: `Answered`
- Question: What exact outcome means Day-100 is successful for you?
- Example: "Daily usable dashboard + reliable alerts + proven useful in decision journal."
- Why this matters: Keeps build scope disciplined and measurable.
- Your answer: Yes to the proposed success direction (usable daily dashboard, reliable alerts, and practical decision value by Day 100).
