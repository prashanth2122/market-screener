Param()

$ErrorActionPreference = "Stop"

Write-Host "[day69] Running email alert dispatch..."
python -c "from market_screener.jobs.email_alert_dispatch import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day69] Email alert dispatch failed."
}
Write-Host "[day69] Email alert dispatch completed."
