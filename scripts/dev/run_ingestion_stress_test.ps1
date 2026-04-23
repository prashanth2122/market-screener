Param()

$ErrorActionPreference = "Stop"

Write-Host "[day39] Running ingestion stress test..."
python -m market_screener.jobs.ingestion_stress
Write-Host "[day39] Ingestion stress test completed."
