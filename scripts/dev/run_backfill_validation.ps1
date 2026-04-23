Param()

$ErrorActionPreference = "Stop"

Write-Host "[day30] Running equity backfill validation..."
python -m market_screener.jobs.backfill_validation
Write-Host "[day30] Equity backfill validation completed."
