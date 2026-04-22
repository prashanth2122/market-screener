# Backend Module

Purpose:
- Data ingestion, normalization, scoring, alerting, and API services.

Directory layout:
- `src/market_screener/` application package
- `tests/` unit and integration tests
- `migrations/` database schema migrations

Stack baseline:
- Python 3.12+
- FastAPI
- PostgreSQL (planned integration)
- Redis (planned integration)

## Quickstart

From repo root:

```powershell
python -m pip install -e .\backend[dev]
python -m uvicorn market_screener.main:app --app-dir .\backend\src --reload --port 8000
```

Run tests:

```powershell
python -m pytest .\backend\tests
```

Migration commands:

```powershell
python -m alembic -c .\backend\alembic.ini upgrade head
python -m alembic -c .\backend\alembic.ini revision -m "describe_change"
```

Configuration management:

- Runtime settings module: `backend/src/market_screener/core/settings.py`
- Settings reload helper (useful for tests): `reload_settings()`
- Safe debug dump with redacted secrets: `as_safe_dict()`

Structured logging:

- JSON log formatter with request correlation IDs
- HTTP middleware emits `request_started` and `request_completed` events
- Response header includes `X-Request-ID`

Health checks:

- `GET /health` for load-balancer and runtime readiness checks
- `GET /api/v1/system/health` for namespaced system diagnostics
- Returns `200` when PostgreSQL and Redis checks are up, otherwise `503`

Provider clients:

- Alpha Vantage wrapper: `backend/src/market_screener/providers/alpha_vantage.py`
- Finnhub wrapper: `backend/src/market_screener/providers/finnhub.py`
- Typed provider exceptions: `backend/src/market_screener/providers/exceptions.py`
- Shared retry policy: `backend/src/market_screener/providers/retry.py`
- Token-bucket rate-limit guard: `backend/src/market_screener/providers/rate_limit.py`

Ingestion jobs:

- Symbol metadata ingestion: `python -m market_screener.jobs.symbol_metadata`
- Job source: `backend/src/market_screener/jobs/symbol_metadata.py`
