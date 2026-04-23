Param()

$ErrorActionPreference = "Stop"

Write-Host "[day57] Running news ingestion..."
python -c "from market_screener.jobs.news_ingestion import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day57] News ingestion failed."
}
Write-Host "[day57] News ingestion completed."
