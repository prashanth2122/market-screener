Param()

$ErrorActionPreference = "Stop"

Write-Host "[day63] Running score explanation payload tests..."
python -m pytest backend/tests/test_score_explanation_payload.py
if ($LASTEXITCODE -ne 0) {
    throw "[day63] Score explanation payload tests failed."
}

Write-Host "[day63] Running score explanation payload smoke..."
python -c "from market_screener.core.score_explanation import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day63] Score explanation payload smoke failed."
}

Write-Host "[day63] Score explanation payload checks completed."
