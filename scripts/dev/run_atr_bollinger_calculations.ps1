Param()

$ErrorActionPreference = "Stop"

Write-Host "[day44] Running ATR/Bollinger indicator calculations smoke check..."
python -m market_screener.core.indicators
Write-Host "[day44] ATR/Bollinger indicator calculations smoke check completed."
