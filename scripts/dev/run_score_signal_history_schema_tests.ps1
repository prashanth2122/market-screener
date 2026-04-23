Param()

$ErrorActionPreference = "Stop"

Write-Host "[day65] Running score and signal history schema tests..."
python -m pytest backend/tests/test_score_signal_history_schema.py
if ($LASTEXITCODE -ne 0) {
    throw "[day65] Score and signal history schema tests failed."
}
Write-Host "[day65] Score and signal history schema tests completed."
