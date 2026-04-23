Param()

$ErrorActionPreference = "Stop"

Write-Host "[day53] Running Piotroski F-score calculation smoke check..."
python -m market_screener.core.piotroski
Write-Host "[day53] Piotroski F-score calculation smoke check completed."
