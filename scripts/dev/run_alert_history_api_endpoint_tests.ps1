Param()

$ErrorActionPreference = "Stop"

Write-Host "[day74] Running alert history API endpoint tests..."
python -m pytest backend/tests/test_alert_history_endpoint.py -q
if ($LASTEXITCODE -ne 0) {
    throw "[day74] Alert history API endpoint tests failed."
}
Write-Host "[day74] Alert history API endpoint tests passed."
