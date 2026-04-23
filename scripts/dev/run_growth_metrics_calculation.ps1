Param()

$ErrorActionPreference = "Stop"

Write-Host "[day55] Running EPS/revenue growth metrics smoke check..."
python -m market_screener.core.growth_metrics
Write-Host "[day55] EPS/revenue growth metrics smoke check completed."
