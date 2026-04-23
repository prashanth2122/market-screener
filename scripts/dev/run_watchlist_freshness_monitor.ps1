Param()

$ErrorActionPreference = "Stop"

Write-Host "[day37] Running watchlist freshness monitor..."
python -m market_screener.jobs.freshness_monitor
Write-Host "[day37] Watchlist freshness monitor completed."
