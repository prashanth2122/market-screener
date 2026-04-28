# Personal Playbook (Signals -> Decisions)

This is the operating manual for using this project in a disciplined way.
It is intentionally opinionated and optimized for swing trades (multi-week to 1 month).

## Core Rules

- The screener is a *shortlist generator*, not an auto-trader.
- Every trade needs: thesis, entry zone, stop, and invalidation.
- Never override risk blocks without a written reason.
- Do not change score weights during the paper-trading loop (Days 91-100). Only adjust transforms, thresholds, cooldowns, and rules after review notes exist.

## Daily Routine (10-20 minutes)

1. Run the screener and export today’s snapshot.
   - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_paper_trading_day.ps1`
2. Review Top 10 by score and mark:
   - "Trade candidate"
   - "Pass (false positive)"
   - "Needs more info"
3. Open detail pages for candidates (chart + news + score explanation).
4. Record paper trades in today’s journal with entry/stop/target.
5. Generate Day 92-style review notes when you have outcomes.

## Signal Meanings (Operational)

### Strong Buy

Action: Plan a trade today or tomorrow.

Checklist:
- Trend regime bullish/accumulation with reasonable confidence
- No major risk flags in last 72h
- Score explanation has no missing major components
- Entry zone can be defined without chasing

Default behavior:
- Put on watchlist immediately
- Create an alert rule for follow-through (breakout confirmation, pullback entry, etc.)

### Buy

Action: Put on watchlist; enter only with a clean technical trigger.

Checklist:
- Trend improving or breakout detected
- Fundamentals not obviously weak (unless you intentionally run a momentum-only play)
- News sentiment not sharply negative

Default behavior:
- Wait for 1 trigger: breakout retest, MA reclaim, or volume confirmation

### Watch

Action: Watchlist only.

Default behavior:
- Set a single "promotion trigger" (what turns it into Buy/Strong Buy)
- Re-check weekly unless new alert fires

### Avoid

Action: Do not trade.

Reasons typically include:
- Risk block true
- Very weak trend regime
- Negative sentiment shock
- Fundamentals/quality breakdown

## Entry / Stop / Target (Swing Template)

- Entry: define a zone, not a single price
- Stop: place where thesis is wrong, not where you "feel pain"
- Target: at least 2R for any trade you take
- Time stop: if nothing happens in 10 trading days, reassess

## Position Sizing (Personal Default)

Use a simple risk model:
- Risk per trade: 0.25% to 1.0% of account (pick one and stick to it for 30 days)
- Max concurrent positions: 5 to 12
- Correlation guard: avoid stacking highly correlated assets (for example, 5 tech mega-caps)

## Alert Hygiene

Alerts are for *decision moments* only.

- Cooldown: keep at 60+ minutes for intraday noise, or 12-24h for swing-only alerts
- Daily cap: keep low (3-10) to preserve attention
- Allowlist: start with `strong_buy,buy` and expand only if you can review more

## Review Loop (Weekly)

Once per week, read the last 7 journals and capture:
- Top false-positive pattern (what fooled you)
- Top false-negative pattern (what you missed)
- One fix to implement next week

Do not implement more than 1-2 changes per week. Make changes measurable.

## "Do Not Do" List

- Do not trade purely because the score is high.
- Do not ignore `blocked_by_risk=true` without a written reason.
- Do not expand symbol universe mid-loop.
- Do not change component weights during validation.
