Param()

$ErrorActionPreference = "Stop"

Write-Host "[day51] Running fundamentals schema tests..."
python -m pytest backend/tests/test_fundamentals_snapshot_schema.py
Write-Host "[day51] Fundamentals schema tests completed."
