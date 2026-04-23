Param()

$ErrorActionPreference = "Stop"

Write-Host "[day42] Running MA50/MA200/RSI14 indicator calculations smoke check..."
python -m market_screener.core.indicators
Write-Host "[day42] Indicator calculations smoke check completed."
