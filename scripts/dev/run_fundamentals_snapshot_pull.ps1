Param()

$ErrorActionPreference = "Stop"

Write-Host "[day52] Running fundamentals snapshot pull..."
python -m market_screener.jobs.fundamentals_snapshot
Write-Host "[day52] Fundamentals snapshot pull completed."
