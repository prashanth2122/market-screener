Param()

$ErrorActionPreference = "Stop"

Write-Host "[day59] Running event risk tagging rules..."
python -c "from market_screener.jobs.event_risk_tagging import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day59] Event risk tagging rules failed."
}
Write-Host "[day59] Event risk tagging rules completed."
