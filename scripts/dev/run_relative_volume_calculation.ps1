Param()

$ErrorActionPreference = "Stop"

Write-Host "[day48] Running relative volume calculation..."
python -m market_screener.jobs.relative_volume
Write-Host "[day48] Relative volume calculation completed."
