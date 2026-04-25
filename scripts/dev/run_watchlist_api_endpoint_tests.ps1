Param()

$ErrorActionPreference = "Stop"

Write-Host "[day73] Running watchlist API endpoint tests..."
python -m pytest backend/tests/test_watchlist_endpoint.py -q
if ($LASTEXITCODE -ne 0) {
    throw "[day73] Watchlist API endpoint tests failed."
}
Write-Host "[day73] Watchlist API endpoint tests passed."
