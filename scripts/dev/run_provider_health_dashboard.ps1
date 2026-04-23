Param()

$ErrorActionPreference = "Stop"

Write-Host "[day38] Running provider health dashboard refresh..."
python -m market_screener.jobs.provider_health_dashboard
Write-Host "[day38] Provider health dashboard refresh completed."
