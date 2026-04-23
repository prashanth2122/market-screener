Param()

$ErrorActionPreference = "Stop"

Write-Host "[day32] Running crypto OHLCV ingestion job..."
python -m market_screener.jobs.crypto_ohlcv
Write-Host "[day32] Crypto OHLCV ingestion completed."
