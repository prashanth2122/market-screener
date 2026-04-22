# Day 1 Success Brief

Date: 22 April 2026
Owner: Prash
Project: Market Screener (Personal Product)

## Product Purpose

Build a personal multi-asset screener that helps identify high-quality swing opportunities with explainable scoring and low-noise alerts.

## Primary User

- Single user: owner-operator (you).
- Usage style: daily swing decision support with expected holding period of at least one month.

## Core Decision Workflow

1. Open screener dashboard and review ranked opportunities.
2. Filter by signal quality, risk flags, and market segment.
3. Inspect top candidates with technical, fundamental, and news context.
4. Receive only high-confidence Telegram alerts (max 5 per day).
5. Track outcomes in validation loop (paper notes + replay + manual review).

## Operating Constraints (Locked)

- Market scope: mixed.
- MVP universe: S&P 500 top 50 + NSE top 50 + Crypto top 50 (150 symbols).
- Timeframe: swing.
- Alerts: Telegram first, capped at 5 actionable alerts/day.
- Negative-news override: enabled (can block buy).
- Deployment target: home server.
- Budget: free-tier-first, mostly zero monthly spend.
- Authentication: basic auth required.

## Hard Guardrails

- Block buy signal when high-risk negative news exists.
- Block buy signal when trend filter fails (price below MA200).
- Block buy signal when liquidity is too low.

## Day-100 Success Definition

Day-100 is successful when all conditions are true:
- Dashboard is used daily for candidate selection.
- Alerts are reliable and low-noise.
- Signals show practical decision value in your validation journal.
- System runs stably on home server without constant manual intervention.

## Explicit Non-Goals (Current Scope)

- No automated trade execution.
- No options-chain analytics.
- No expensive data dependencies in MVP.

## Day 1 Completion Status

- Success criteria: completed.
- Operating constraints: completed.
- User workflow: completed.
- Day-100 definition: completed.
