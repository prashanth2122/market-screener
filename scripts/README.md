# Scripts Module

Purpose:
- Utility scripts for development, operations, and maintenance automation.

Initial subdirectories:
- `dev/` local developer workflows
- `ops/` operational and maintenance scripts

Guideline:
- Scripts should be idempotent and documented with usage notes.

## Unified Local Stack Utility

- Single file to start/stop/check full local stack (PostgreSQL + Redis + backend + frontend):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action start`
- Check stack status:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action status`
- Stop stack:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action stop`
- VS Code Run and Debug entries are available in `.vscode/launch.json`:
`Local Stack: Start`, `Local Stack: Status`, `Local Stack: Stop`

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

## Day 54 Utility

- Run Altman Z-score calculation smoke check:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_altman_z_score_calculation.ps1`

## Day 55 Utility

- Run EPS/revenue growth metrics smoke check:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_growth_metrics_calculation.ps1`

## Day 56 Utility

- Run fundamentals quality normalization smoke check:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_fundamentals_quality_normalization.ps1`

## Day 57 Utility

- Run news ingestion pull:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_news_ingestion.ps1`

## Day 58 Utility

- Run sentiment scoring pipeline:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_sentiment_scoring_pipeline.ps1`

## Day 59 Utility

- Run event risk tagging rules:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_event_risk_tagging_rules.ps1`
- VS Code Run and Debug presets:
`Day 59: Event Risk Tagging (Python)`, `Day 59: Event Risk Rules (Core Smoke)`

## Day 60 Utility

- Run sentiment + event-risk combined test suite:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_sentiment_risk_pipeline_tests.ps1`
- VS Code Run and Debug preset:
`Day 60: Sentiment + Risk Tests`

## Day 61 Utility

- Run score factor transform checks + smoke:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_score_factor_transform_checks.ps1`
- VS Code Run and Debug preset:
`Day 61: Score Factor Checks`

## Day 62 Utility

- Run composite score engine checks + smoke:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_composite_score_engine_v1.ps1`
- VS Code Run and Debug preset:
`Day 62: Composite Score Engine Checks`

## Day 63 Utility

- Run score explanation payload checks + smoke:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_score_explanation_payload_checks.ps1`
- VS Code Run and Debug preset:
`Day 63: Score Explanation Payload Checks`

## Day 64 Utility

- Run signal mapping rule checks + smoke:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_signal_mapping_rules_checks.ps1`
- VS Code Run and Debug preset:
`Day 64: Signal Mapping Rule Checks`

## Day 65 Utility

- Run score + signal history schema tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_score_signal_history_schema_tests.ps1`
- VS Code Run and Debug preset:
`Day 65: Score/Signal History Schema Tests`

## Day 66 Utility

- Run score + signal 90-day backfill:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_score_signal_backfill_90d.ps1`
- VS Code Run and Debug preset:
`Day 66: Score/Signal Backfill Tests`

## Day 69 Utility

- Run email alert dispatch:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_email_alert_dispatch.ps1`
- VS Code Run and Debug preset:
`Day 69: Email Alert Dispatch Tests`
