# Launch v1 (Personal)

Date: 2026-04-28

This marks the start of "personal v1" usage and the weekly improvement cycle.

## One-Time Launch Steps

1. Run final QA (recommended default skips npm audit because it may require major Next upgrades):
   - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_final_qa.ps1 -SkipNpmAudit`
2. Start the local stack:
   - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action start`
3. Create a DB backup:
   - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_db_backup.ps1`

## Daily Operating Steps (Swing Workflow)

1. Paper-trading snapshot + journal:
   - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_paper_trading_day.ps1 -Limit 50 -Symbol AAPL`
2. Review false positives / false negatives:
   - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_paper_trading_review.ps1 -Top 10`
3. Optional daily digest:
   - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_daily_digest.ps1`

## Weekly Cadence (Improvement Cycle)

Once per week:
- Read the last 7 journals and reviews in `docs/paper_trading/`
- Pick 1-2 fixes maximum (measurable) for next week
- Prefer: transforms, thresholds, rules, data quality, and alert hygiene
- Avoid: weight changes unless you have repeated evidence across multiple weeks

Suggested weekly checks:
- Reliability: run a 12-24h soak test:
  - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_reliability_soak_test.ps1 -DurationMinutes 1440 -IntervalSeconds 60 -StartStack`
- Report: generate a soak report:
  - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_soak_report.ps1 -LogFile logs/soak/<soak_file>.jsonl`

## Definitions of Done (v1)

- You can run the stack daily without babysitting
- Alerts are low-noise (daily cap + cooldown respected)
- You can restore from backup successfully
- You have weekly notes that drive small, controlled changes

## Single Command (Optional)

- Launch helper (runs QA, then starts stack unless `-NoStartStack`):
  - `powershell -ExecutionPolicy Bypass -File scripts/dev/run_launch_v1.ps1 -SkipNpmAudit`
