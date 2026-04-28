# Runbook (Maintenance + Failures)

Scope: personal, local-first operation with Docker Compose.

## Start/Stop/Status

- Start stack: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action start`
- Status: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action status`
- Stop stack: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action stop`

## Health Checks

- Backend ping: `http://localhost:8000/api/v1/system/ping`
- Backend health: `http://localhost:8000/health`
- Provider dashboard read: `http://localhost:8000/api/v1/system/provider-health`

Optional (disabled by default):
- Slow queries: `http://localhost:8000/api/v1/system/slow-queries`
  - Enable via `.env`: `DB_SLOW_QUERY_ENDPOINT_ENABLED=true`

## Common Failures + Fixes

### Backend Not Reachable

Symptoms:
- `curl`/browser can’t connect to `localhost:8000`

Fix:
1. `scripts/dev/run_local_stack.ps1 -Action status`
2. If containers are down: `scripts/dev/run_local_stack.ps1 -Action start`
3. Check backend container logs: `docker logs market-screener-backend --tail 200`

### Postgres Not Healthy

Symptoms:
- Compose shows postgres unhealthy
- migrations fail

Fix:
1. Run connectivity check: `powershell -ExecutionPolicy Bypass -File scripts/dev/check_postgres.ps1`
2. Inspect logs: `docker logs market-screener-postgres --tail 200`
3. If volume is corrupted and you accept data loss, remove volume and recreate (manual step; do only if you have backups).

### Migrations Fail

Fix:
- Run migrations explicitly: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_migrations.ps1`
- If a migration is missing locally, re-pull the repo state (git).

### Ingestion Failures / Retries

Tools:
- Retry due failures: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_ingestion_failure_retry.ps1`
- Replay time window: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_ingestion_failure_replay.ps1 -SinceHours 24 -Limit 200`

If failures are non-retryable normalization errors:
- They go to the DLQ table (Day 83); fix the parser/normalizer and re-run ingestion.

### Alert Spam / Too Many Alerts

Fix:
1. Tighten allowlist: `ALERT_DISPATCH_SIGNAL_ALLOWLIST=strong_buy,buy`
2. Increase cooldown: `ALERT_COOLDOWN_MINUTES=720` (swing-only)
3. Reduce daily cap: `ALERT_MAX_PER_DAY=3`

Validate:
- `powershell -ExecutionPolicy Bypass -File scripts/dev/run_alert_threshold_cooldown_tests.ps1`

### Frontend Doesn’t Load / Build Fails

Fix:
1. Run checks: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_frontend_screener_table_checks.ps1`
2. Reset node_modules if needed: delete `frontend/node_modules` and rerun `npm install`

## Backups

- Backup DB: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_db_backup.ps1`
- Restore DB (destructive, requires -Force): `powershell -ExecutionPolicy Bypass -File scripts/dev/run_db_restore.ps1 -BackupFile backups/<file>.dump -Force`

## Soak Testing

- Start a soak (example 60 minutes): `powershell -ExecutionPolicy Bypass -File scripts/dev/run_reliability_soak_test.ps1 -DurationMinutes 60 -IntervalSeconds 60 -StartStack`
- Report: `powershell -ExecutionPolicy Bypass -File scripts/dev/run_soak_report.ps1 -LogFile logs/soak/<soak_file>.jsonl`
