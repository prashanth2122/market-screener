Param()

$ErrorActionPreference = "Stop"

Write-Host "[day94] Running alert threshold + cooldown tests..." -ForegroundColor Cyan
python -m pytest -q backend/tests/test_email_alert_dispatch_job.py backend/tests/test_telegram_alert_dispatch_job.py
if ($LASTEXITCODE -ne 0) {
    throw "[day94] Alert threshold + cooldown tests failed."
}
Write-Host "[day94] Alert threshold + cooldown tests passed." -ForegroundColor Green
