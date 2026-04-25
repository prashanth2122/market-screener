Param()

$ErrorActionPreference = "Stop"

Write-Host "[day72] Running asset detail API endpoint tests..."
python -m pytest backend/tests/test_asset_detail_endpoint.py -q
if ($LASTEXITCODE -ne 0) {
    throw "[day72] Asset detail API endpoint tests failed."
}
Write-Host "[day72] Asset detail API endpoint tests passed."
