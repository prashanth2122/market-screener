Param()

$ErrorActionPreference = "Stop"

Write-Host "[day46] Running trend regime classification..."
python -m market_screener.jobs.trend_regime
Write-Host "[day46] Trend regime classification completed."
