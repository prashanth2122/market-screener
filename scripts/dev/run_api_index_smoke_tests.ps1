Param()

$ErrorActionPreference = "Stop"

Write-Host "[day86] Running API index metadata smoke tests..."
python -m pytest -q backend/tests/test_index_metadata_smoke.py
if ($LASTEXITCODE -ne 0) {
    throw "[day86] API index metadata smoke tests failed."
}
Write-Host "[day86] API index metadata smoke tests passed."
