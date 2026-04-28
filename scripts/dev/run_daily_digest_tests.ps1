Param()

$ErrorActionPreference = "Stop"

Write-Host "[day95] Running daily digest tests..." -ForegroundColor Cyan
python -m pytest -q backend/tests/test_daily_digest_job.py
if ($LASTEXITCODE -ne 0) {
    throw "[day95] Daily digest tests failed."
}
Write-Host "[day95] Daily digest tests passed." -ForegroundColor Green
