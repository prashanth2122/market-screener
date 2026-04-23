Param()

$ErrorActionPreference = "Stop"

Write-Host "[day45] Running indicator snapshot refresh..."
python -m market_screener.jobs.indicator_snapshot
Write-Host "[day45] Indicator snapshot refresh completed."
