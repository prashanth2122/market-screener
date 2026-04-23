Param()

$ErrorActionPreference = "Stop"

Write-Host "[day54] Running Altman Z-score calculation smoke check..."
python -m market_screener.core.altman
Write-Host "[day54] Altman Z-score calculation smoke check completed."
