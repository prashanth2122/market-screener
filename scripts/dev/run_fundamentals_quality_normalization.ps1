Param()

$ErrorActionPreference = "Stop"

Write-Host "[day56] Running fundamentals quality normalization smoke check..."
python -m market_screener.core.fundamentals_quality
Write-Host "[day56] Fundamentals quality normalization smoke check completed."
