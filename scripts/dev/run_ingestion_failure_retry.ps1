Param()

$ErrorActionPreference = "Stop"

Write-Host "[day29] Running ingestion failure retry job..."
python -m market_screener.jobs.ingestion_retry
Write-Host "[day29] Ingestion failure retry completed."
