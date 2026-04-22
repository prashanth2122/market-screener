# Docker Stack (Day 13)

This stack brings up:
- `postgres` (primary database)
- `redis` (cache/queue)
- `backend` (FastAPI service)

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- Root `.env` file present (`copy .env.example .env`)

## Start Stack

From repo root:

```powershell
docker compose -f .\infra\docker\docker-compose.yml up --build -d
```

## Check Status

```powershell
docker compose -f .\infra\docker\docker-compose.yml ps
```

Backend health route:
- `http://localhost:8000/api/v1/system/ping`

## Stop Stack

```powershell
docker compose -f .\infra\docker\docker-compose.yml down
```

To also remove persisted DB/cache volumes:

```powershell
docker compose -f .\infra\docker\docker-compose.yml down -v
```
