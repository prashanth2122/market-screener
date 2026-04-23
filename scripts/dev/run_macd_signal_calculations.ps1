Param()

$ErrorActionPreference = "Stop"

Write-Host "[day43] Running MACD/signal indicator calculations smoke check..."
python -m market_screener.core.indicators
Write-Host "[day43] MACD/signal indicator calculations smoke check completed."
