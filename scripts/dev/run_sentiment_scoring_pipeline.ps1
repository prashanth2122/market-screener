Param()

$ErrorActionPreference = "Stop"

Write-Host "[day58] Running sentiment scoring pipeline..."
python -c "from market_screener.jobs.sentiment_scoring import main; main()"
if ($LASTEXITCODE -ne 0) {
    throw "[day58] Sentiment scoring pipeline failed."
}
Write-Host "[day58] Sentiment scoring pipeline completed."
