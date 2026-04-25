Param()

$ErrorActionPreference = "Stop"

Write-Host "[day71] Running screener API endpoint tests..."
python -m pytest backend/tests/test_screener_endpoint.py -q
if ($LASTEXITCODE -ne 0) {
    throw "[day71] Screener API endpoint tests failed."
}
Write-Host "[day71] Screener API endpoint tests passed."
