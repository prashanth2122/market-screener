# Scripts Module

Purpose:
- Utility scripts for development, operations, and maintenance automation.

Initial subdirectories:
- `dev/` local developer workflows
- `ops/` operational and maintenance scripts

Guideline:
- Scripts should be idempotent and documented with usage notes.

## Day 14 Utility

- PostgreSQL connectivity check:
`powershell -ExecutionPolicy Bypass -File scripts/dev/check_postgres.ps1`

## Day 15 Utility

- Run migrations to latest revision:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_migrations.ps1`

## Day 25 Utility

- Run symbol metadata ingestion job:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_symbol_metadata_ingestion.ps1`

## Day 26 Utility

- Run equity OHLCV ingestion job:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_equity_ohlcv_ingestion.ps1`

## Day 29 Utility

- Run ingestion failure retry workflow:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_ingestion_failure_retry.ps1`

## Day 30 Utility

- Run equity 7-day backfill validation for 20 symbols:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_backfill_validation.ps1`

## Day 32 Utility

- Run crypto OHLCV ingestion job:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_crypto_ohlcv_ingestion.ps1`

## Day 33 Utility

- Run forex/commodity OHLCV ingestion job:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_macro_ohlcv_ingestion.ps1`

## Day 37 Utility

- Run watchlist freshness monitor job:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_watchlist_freshness_monitor.ps1`

## Day 38 Utility

- Run provider latency/success dashboard refresh job:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_provider_health_dashboard.ps1`

## Day 39 Utility

- Run ingestion stress test for up to configured active symbols:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_ingestion_stress_test.ps1`

## Day 41 Utility

- Check TA library integration availability:
`powershell -ExecutionPolicy Bypass -File scripts/dev/check_ta_library.ps1`

## Day 42 Utility

- Run MA50/MA200/RSI14 indicator calculation smoke check:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_indicator_calculations.ps1`

## Day 43 Utility

- Run MACD/signal indicator calculation smoke check:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_macd_signal_calculations.ps1`

## Day 44 Utility

- Run ATR/Bollinger indicator calculation smoke check:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_atr_bollinger_calculations.ps1`

## Day 45 Utility

- Run indicator snapshot refresh writes:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_indicator_snapshot_refresh.ps1`

## Day 46 Utility

- Run trend regime classification:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_trend_regime_classification.ps1`

## Day 47 Utility

- Run breakout detection:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_breakout_detection.ps1`

## Day 48 Utility

- Run relative volume calculation:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_relative_volume_calculation.ps1`

## Day 49 Utility

- Run indicator fixture-based unit tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_indicator_fixture_tests.ps1`

## Day 50 Utility

- Run indicator reference-value validation:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_indicator_reference_validation.ps1`

## Day 51 Utility

- Run fundamentals schema tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_fundamentals_schema_tests.ps1`

## Day 52 Utility

- Run fundamentals snapshot pull job:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_fundamentals_snapshot_pull.ps1`

## Day 53 Utility

- Run Piotroski F-score calculation smoke check:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_piotroski_f_score_calculation.ps1`
