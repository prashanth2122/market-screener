Param()

$ErrorActionPreference = "Stop"

Write-Host "[day33] Running forex/commodity OHLCV ingestion job..."
python -m market_screener.jobs.macro_ohlcv
Write-Host "[day33] Forex/commodity OHLCV ingestion completed."
