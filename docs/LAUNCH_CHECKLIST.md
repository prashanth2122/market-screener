# Launch Checklist (Personal v1)

Goal: ship a stable personal v1 that you can run daily without babysitting.

## Pre-Launch (One Time)

- [ ] `.env` exists and secrets are not committed
- [ ] Postgres/Redis/backend start cleanly via `scripts/dev/run_local_stack.ps1`
- [ ] Migrations run cleanly
- [ ] Screener endpoint returns data (even if seeded)
- [ ] Asset detail endpoint returns data for at least 1 symbol
- [ ] Alerts are configured (Telegram at minimum) or explicitly disabled
- [ ] Backups directory exists and you can create a backup

## “No Regrets” Defaults

- Signal allowlist: `strong_buy,buy`
- Cooldown: 12-24h for swing-only usage
- Daily cap: 3-10
- Paper-trading journal enabled (Days 91-100)

## Final QA Pass (Repeatable)

Run:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_final_qa.ps1`

Done when:
- All checks pass
- You can run one paper-trading day flow end-to-end:
  - `scripts/dev/run_paper_trading_day.ps1`
  - `scripts/dev/run_paper_trading_review.ps1`

## Go/No-Go

Go if:
- Ingestion jobs don’t fail repeatedly
- Soak test shows low/no request failure rate
- Alerts are low-noise and actionable

No-Go if:
- You see alert spam
- Screener/asset endpoints are frequently failing
- You can’t restore from a backup
