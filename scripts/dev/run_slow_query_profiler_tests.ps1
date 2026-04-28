Param()

$ErrorActionPreference = "Stop"

Write-Host "[day85] Running slow query profiler tests..."
python -m pytest -q backend/tests/test_slow_query_profiler.py
if ($LASTEXITCODE -ne 0) {
    throw "[day85] Slow query profiler tests failed."
}
Write-Host "[day85] Slow query profiler tests passed."
