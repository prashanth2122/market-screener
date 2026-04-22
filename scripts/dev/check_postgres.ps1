param(
    [string]$ComposeFile = "infra/docker/docker-compose.yml",
    [string]$ContainerName = "market-screener-postgres",
    [string]$DbName = "market_screener",
    [string]$DbUser = "market_user"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
}

Write-Host "Starting PostgreSQL service..." -ForegroundColor Cyan
docker compose -f $ComposeFile up -d postgres | Out-Null

Write-Host "Waiting for PostgreSQL health..." -ForegroundColor Cyan
$healthy = $false
for ($i = 0; $i -lt 20; $i++) {
    $status = docker inspect -f "{{.State.Health.Status}}" $ContainerName 2>$null
    if ($status -eq "healthy") {
        $healthy = $true
        break
    }
    Start-Sleep -Seconds 2
}

if (-not $healthy) {
    throw "PostgreSQL did not reach healthy state within timeout."
}

Write-Host "Running SQL connectivity check..." -ForegroundColor Cyan
docker exec $ContainerName psql -U $DbUser -d $DbName -c "SELECT current_database() AS db, current_user AS usr, now() AS checked_at;"

Write-Host "Checking localhost port 5432..." -ForegroundColor Cyan
Test-NetConnection -ComputerName localhost -Port 5432 | Select-Object ComputerName, RemotePort, TcpTestSucceeded

Write-Host "PostgreSQL connectivity check passed." -ForegroundColor Green
