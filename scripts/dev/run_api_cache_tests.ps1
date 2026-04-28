Param()

$ErrorActionPreference = "Stop"

Write-Host "[day84] Running API response cache tests..."
python -m pytest -q backend/tests/test_api_response_cache.py
if ($LASTEXITCODE -ne 0) {
    throw "[day84] API response cache tests failed."
}
Write-Host "[day84] API response cache tests passed."
