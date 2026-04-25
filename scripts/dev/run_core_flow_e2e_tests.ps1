Param()

$ErrorActionPreference = "Stop"

Write-Host "[day81] Running core flow E2E API tests..."
python -m pytest -q backend/tests/test_core_flow_e2e.py
if ($LASTEXITCODE -ne 0) {
    throw "[day81] Core flow E2E tests failed."
}
Write-Host "[day81] Core flow E2E tests passed."
