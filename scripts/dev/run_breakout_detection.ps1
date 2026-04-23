Param()

$ErrorActionPreference = "Stop"

Write-Host "[day47] Running breakout detection..."
python -m market_screener.jobs.breakout_detection
Write-Host "[day47] Breakout detection completed."
