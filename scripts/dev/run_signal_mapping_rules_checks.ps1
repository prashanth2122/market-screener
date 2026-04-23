Param()

$ErrorActionPreference = "Stop"

Write-Host "[day64] Running signal mapping rule tests..."
python -m pytest backend/tests/test_signal_mapping_rules.py
if ($LASTEXITCODE -ne 0) {
    throw "[day64] Signal mapping rule tests failed."
}

Write-Host "[day64] Running signal mapping rule smoke..."
python -c "from market_screener.core.signal_mapping import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day64] Signal mapping rule smoke failed."
}

Write-Host "[day64] Signal mapping rule checks completed."
