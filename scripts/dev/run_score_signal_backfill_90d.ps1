Param()

$ErrorActionPreference = "Stop"

Write-Host "[day66] Running score + signal 90-day backfill..."
python -c "from market_screener.jobs.score_signal_backfill import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day66] Score + signal 90-day backfill failed."
}
Write-Host "[day66] Score + signal 90-day backfill completed."
