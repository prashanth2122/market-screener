param(
    [string]$ComposeFile = "infra/docker/docker-compose.yml"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
}

Write-Host "Starting PostgreSQL and Redis..." -ForegroundColor Cyan
docker compose -f $ComposeFile up -d postgres redis | Out-Null

Write-Host "Running Alembic upgrade head in backend container..." -ForegroundColor Cyan
docker compose -f $ComposeFile run --rm backend python -m alembic -c /app/alembic.ini upgrade head

Write-Host "Migration command completed." -ForegroundColor Green
