# Contributing Standards

Date: 22 April 2026
Project: Market Screener
Scope: Solo-first engineering standards for consistent, production-grade delivery

## 1) Core Principles

- Prefer clarity over cleverness.
- Keep changes small and auditable.
- Never compromise data correctness for speed.
- Treat reliability and observability as first-class requirements.

## 2) Repository Conventions

- `backend/`: ingestion, analytics, scoring, alerting, API.
- `frontend/`: dashboard UI.
- `infra/`: deployment and monitoring assets.
- `scripts/`: automation helpers.
- `config/`: versioned static configuration.
- `docs/`: architecture, execution, and runbooks.

## 3) Language and Formatting Standards

### Python (backend/scripts)
- Formatter: `black`
- Linter: `ruff`
- Import sorting: `ruff` (isort rules)
- Type checking target: gradual `mypy` adoption for core modules
- Style baseline:
- line length 100
- explicit type hints for public functions
- no wildcard imports

### TypeScript (frontend)
- Formatter: `prettier`
- Linter: `eslint` with TypeScript rules
- Type checking: `tsc --noEmit`
- Style baseline:
- strict mode enabled
- avoid `any` unless documented with justification
- keep components focused and testable

## 4) Naming Conventions

### Files and directories
- Python modules: `snake_case.py`
- TypeScript files: `kebab-case.ts` or `kebab-case.tsx`
- React components: `PascalCase` export names
- Tests:
- Python: `test_*.py`
- Frontend: `*.test.ts` or `*.test.tsx`

### Identifiers
- Python variables/functions: `snake_case`
- Python classes: `PascalCase`
- TypeScript variables/functions: `camelCase`
- Constants: `UPPER_SNAKE_CASE`

## 5) Branch Strategy

- Default branch naming prefix: `codex/`
- Pattern: `codex/<area>-<short-description>`
- Examples:
- `codex/backend-ingestion-base`
- `codex/frontend-screener-table`
- `codex/docs-acceptance-checklist`

## 6) Commit Message Standard

Use Conventional Commits style:
- `feat: ...`
- `fix: ...`
- `docs: ...`
- `refactor: ...`
- `test: ...`
- `chore: ...`

Examples:
- `feat: add provider fallback router for equities`
- `fix: block strong-buy when ma200 trend fails`
- `docs: add day-8 acceptance checklist`

Rules:
- subject line in imperative mood
- keep subject concise
- explain why in commit body when change is non-trivial

## 7) Pull Request/Review Checklist

Before merging, confirm:
- formatting and lint pass
- relevant tests added or updated
- no secrets or credentials in code
- docs updated for behavior/config changes
- migration notes added for schema changes
- rollback path is clear for risky changes

## 8) Testing Expectations

- Every bug fix should include a regression test where practical.
- Core logic (scoring, rule engine, normalization) requires unit tests.
- Integration tests required for provider adapters and ingestion flow.
- Keep test data deterministic and versioned.

## 9) Security and Secrets

- Never commit `.env` or raw credentials.
- Use `.env.example` for variable templates only.
- Mask sensitive values in logs and screenshots.
- Rotate keys immediately if exposure is suspected.

## 10) Documentation Rules

- Any behavior change must update at least one relevant doc.
- Execution progress must be recorded in `docs/EXECUTION_LOG.md`.
- Scope or acceptance changes must update:
- `docs/scope_matrix.md`
- `docs/IMPLEMENTATION_SPEC.md`

## 11) Definition of Done for a Change

A change is done only when:
- code quality checks pass
- required tests pass
- docs are updated
- operational impact is known
- change can be explained in under 2 minutes

## 12) Local Quality Gate Commands

- Install hooks:
`python -m pre_commit install`

- Run on all tracked files:
`python -m pre_commit run --all-files`

- Run on specific files:
`python -m pre_commit run --files <file1> <file2>`
