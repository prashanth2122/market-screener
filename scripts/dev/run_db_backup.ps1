param(
    [string]$ComposeFile = "infra/docker/docker-compose.yml",
    [string]$ContainerName = "market-screener-postgres",
    [string]$DbName = "market_screener",
    [string]$DbUser = "market_user",
    [string]$OutDir = "backups",
    [ValidateSet("custom", "plain")]
    [string]$Format = "custom"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeDb = ($DbName -replace "[^a-zA-Z0-9_\\-]", "_")
$extension = if ($Format -eq "plain") { "sql" } else { "dump" }
$backupName = "${safeDb}_${timestamp}.${extension}"
$outPath = Join-Path $repoRoot $OutDir
$destFile = Join-Path $outPath $backupName

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & docker compose -f $ComposeFile @Args
}

function Wait-PostgresHealthy {
    param([int]$TimeoutSeconds = 60)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $status = docker inspect -f "{{.State.Health.Status}}" $ContainerName 2>$null
        if ($status -eq "healthy") {
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "PostgreSQL did not reach healthy state within $TimeoutSeconds seconds."
}

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $outPath | Out-Null

    Write-Host "[day87] Ensuring postgres service is running..." -ForegroundColor Cyan
    Invoke-Compose up -d postgres | Out-Null
    Wait-PostgresHealthy -TimeoutSeconds 60

    $containerTmp = "/tmp/$backupName"

    if ($Format -eq "plain") {
        Write-Host "[day87] Creating plain SQL dump in container..." -ForegroundColor Cyan
        docker exec $ContainerName pg_dump -U $DbUser -d $DbName --no-owner --no-privileges -f $containerTmp
    }
    else {
        Write-Host "[day87] Creating custom-format dump in container..." -ForegroundColor Cyan
        docker exec $ContainerName pg_dump -U $DbUser -d $DbName --no-owner --no-privileges -Fc -f $containerTmp
    }

    Write-Host "[day87] Copying backup to host: $destFile" -ForegroundColor Cyan
    docker cp "${ContainerName}:${containerTmp}" $destFile
    docker exec $ContainerName rm -f $containerTmp | Out-Null

    Write-Host "[day87] DB backup complete: $destFile" -ForegroundColor Green
}
finally {
    Pop-Location
}
