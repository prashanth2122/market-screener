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
