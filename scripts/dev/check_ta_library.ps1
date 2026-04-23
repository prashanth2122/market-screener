Param()

$ErrorActionPreference = "Stop"

Write-Host "[day41] Checking TA library integration..."
python -m market_screener.core.ta_library
Write-Host "[day41] TA library integration check completed."
