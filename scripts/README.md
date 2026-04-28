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

## Day 70 Utility

- Run Telegram alert dispatch:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_telegram_alert_dispatch.ps1`
- VS Code Run and Debug preset:
`Day 70: Telegram Alert Dispatch Tests`

## Day 71 Utility

- Run screener API endpoint tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_screener_api_endpoint_tests.ps1`
- VS Code Run and Debug preset:
`Day 71: Screener Endpoint Tests`

## Day 72 Utility

- Run asset detail API endpoint tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_asset_detail_api_endpoint_tests.ps1`
- VS Code Run and Debug preset:
`Day 72: Asset Detail Endpoint Tests`

## Day 73 Utility

- Run watchlist API endpoint tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_watchlist_api_endpoint_tests.ps1`
- VS Code Run and Debug preset:
`Day 73: Watchlist Endpoint Tests`

## Day 74 Utility

- Run alert history API endpoint tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_alert_history_api_endpoint_tests.ps1`
- VS Code Run and Debug preset:
`Day 74: Alert History Endpoint Tests`

## Day 75 Utility

- Run frontend screener table quality checks:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_frontend_screener_table_checks.ps1`
- VS Code Run and Debug preset:
`Day 75: Frontend Screener Checks`

## Day 81 Utility

- Run core flow end-to-end API tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_core_flow_e2e_tests.ps1`

## Day 82 Utility

- Replay ingestion failures for a time window:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_ingestion_failure_replay.ps1 -SinceHours 24 -Limit 200`

## Day 83 Utility

- Run dead-letter queue tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_dead_letter_queue_tests.ps1`

## Day 84 Utility

- Run API response cache tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_api_cache_tests.ps1`

## Day 85 Utility

- Run slow query profiler tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_slow_query_profiler_tests.ps1`

## Day 86 Utility

- Run API index metadata smoke tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_api_index_smoke_tests.ps1`

## Day 87 Utility

- Create a timestamped DB backup (custom-format):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_db_backup.ps1`
- Restore a DB backup (requires explicit `-Force`):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_db_restore.ps1 -BackupFile backups/market_screener_YYYYMMDD_HHMMSS.dump -Force`

## Day 88 Utility

- Run secrets and dependency security checks:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_security_checks.ps1`

## Day 89 Utility

- Run reliability soak test (default 60 minutes):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_reliability_soak_test.ps1`
- Run a 7-day soak (10080 minutes) with 60s interval:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_reliability_soak_test.ps1 -DurationMinutes 10080 -IntervalSeconds 60`

## Day 90 Utility

- Generate a report from a soak JSONL log:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_soak_report.ps1 -LogFile logs/soak/soak_YYYYMMDD_HHMMSS.jsonl`

## Day 91 Utility

- Create today's paper-trading journal + screener snapshot:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_paper_trading_day.ps1 -Date 2026-04-28 -Limit 50 -Symbol AAPL`

## Day 92 Utility

- Generate a Day 92 review file from an existing snapshot:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_paper_trading_review.ps1 -Date 2026-04-28 -Top 10`

## Day 93 Utility

- Run score transform profile checks (transforms only, no weight changes):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_score_transform_profile_checks.ps1`

## Day 94 Utility

- Run alert threshold + cooldown tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_alert_threshold_cooldown_tests.ps1`

## Day 95 Utility

- Run daily digest job (telegram/email depending on settings):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_daily_digest.ps1`
- Run daily digest tests:
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_daily_digest_tests.ps1`

## Day 97 Utility

- Run model version freeze checks (ensures changelog entry exists for `SCORE_MODEL_VERSION`):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_model_version_freeze_checks.ps1`

## Day 99 Utility

- Run final QA (recommended before "launch"):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_final_qa.ps1 -SkipNpmAudit`

## Day 100 Utility

- Run launch sequence (final QA + start stack):
`powershell -ExecutionPolicy Bypass -File scripts/dev/run_launch_v1.ps1 -SkipNpmAudit`
