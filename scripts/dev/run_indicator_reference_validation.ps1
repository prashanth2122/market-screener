Param()

$ErrorActionPreference = "Stop"

Write-Host "[day50] Running indicator reference validation..."
python -m market_screener.core.indicator_reference_validation
Write-Host "[day50] Indicator reference validation completed."
