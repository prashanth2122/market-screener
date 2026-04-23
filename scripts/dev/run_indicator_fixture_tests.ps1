Param()

$ErrorActionPreference = "Stop"

Write-Host "[day49] Running indicator fixture-based unit tests..."
python -m pytest backend/tests/test_indicator_known_fixtures.py
Write-Host "[day49] Indicator fixture-based unit tests completed."
