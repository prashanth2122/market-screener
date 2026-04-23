Param()

$ErrorActionPreference = "Stop"

Write-Host "[day26] Running equity OHLCV ingestion job..."
python -m market_screener.jobs.equity_ohlcv
Write-Host "[day26] Equity OHLCV ingestion completed."
