Param()

$ErrorActionPreference = "Stop"

Write-Host "[day70] Running Telegram alert dispatch..."
python -c "from market_screener.jobs.telegram_alert_dispatch import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day70] Telegram alert dispatch failed."
}
Write-Host "[day70] Telegram alert dispatch completed."
