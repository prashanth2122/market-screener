Param()

$ErrorActionPreference = "Stop"

Write-Host "[day83] Running dead-letter queue tests..."
python -m pytest -q backend/tests/test_dead_letter_queue.py
if ($LASTEXITCODE -ne 0) {
    throw "[day83] Dead-letter queue tests failed."
}
Write-Host "[day83] Dead-letter queue tests passed."
