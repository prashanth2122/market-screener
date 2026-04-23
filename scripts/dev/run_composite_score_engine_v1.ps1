Param()

$ErrorActionPreference = "Stop"

Write-Host "[day62] Running composite score engine tests..."
python -m pytest backend/tests/test_composite_score_engine.py
if ($LASTEXITCODE -ne 0) {
    throw "[day62] Composite score engine tests failed."
}

Write-Host "[day62] Running composite score engine smoke..."
python -c "from market_screener.core.composite_score import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day62] Composite score engine smoke failed."
}

Write-Host "[day62] Composite score engine checks completed."
