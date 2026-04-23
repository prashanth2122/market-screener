Param()

$ErrorActionPreference = "Stop"

Write-Host "[day61] Running score factor transform checks..."
python -m pytest backend/tests/test_score_factor_transforms.py
if ($LASTEXITCODE -ne 0) {
    throw "[day61] Score factor transform checks failed."
}

Write-Host "[day61] Running score factor transform smoke..."
python -c "from market_screener.core.score_factors import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day61] Score factor transform smoke failed."
}

Write-Host "[day61] Score factor transform checks completed."
