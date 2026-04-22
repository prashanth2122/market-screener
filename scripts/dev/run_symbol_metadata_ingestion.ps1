Param()

$ErrorActionPreference = "Stop"

Write-Host "[day25] Running symbol metadata ingestion job..."
python -m market_screener.jobs.symbol_metadata
Write-Host "[day25] Symbol metadata ingestion completed."
