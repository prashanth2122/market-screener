Param()

$ErrorActionPreference = "Stop"

Write-Host "[day95] Running daily digest job..." -ForegroundColor Cyan
python -m market_screener.jobs.daily_digest
if ($LASTEXITCODE -ne 0) {
    throw "[day95] Daily digest job failed."
}
Write-Host "[day95] Daily digest job completed." -ForegroundColor Green
