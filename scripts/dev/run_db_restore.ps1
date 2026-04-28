param(
    [string]$ComposeFile = "infra/docker/docker-compose.yml",
    [string]$ContainerName = "market-screener-postgres",
    [string]$DbName = "market_screener",
    [string]$DbUser = "market_user",
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [switch]$Clean,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$resolvedBackup = (Resolve-Path $BackupFile).Path

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

if (-not $Force) {
    throw "[day87] Refusing to restore without -Force (restore is destructive)."
}

$extension = [System.IO.Path]::GetExtension($resolvedBackup).ToLowerInvariant()
$isPlain = $extension -eq ".sql"

Push-Location $repoRoot
try {
    Write-Host "[day87] Ensuring postgres service is running..." -ForegroundColor Cyan
    Invoke-Compose up -d postgres | Out-Null
    Wait-PostgresHealthy -TimeoutSeconds 60

    $backupName = [System.IO.Path]::GetFileName($resolvedBackup)
    $containerTmp = "/tmp/$backupName"

    Write-Host "[day87] Copying backup into container..." -ForegroundColor Cyan
    docker cp $resolvedBackup "${ContainerName}:${containerTmp}"

    if ($isPlain) {
        Write-Host "[day87] Restoring from plain SQL..." -ForegroundColor Cyan
        docker exec $ContainerName psql -U $DbUser -d $DbName -f $containerTmp
    }
    else {
        $restoreArgs = @("pg_restore", "-U", $DbUser, "-d", $DbName)
        if ($Clean) {
            $restoreArgs += @("--clean", "--if-exists")
        }
        $restoreArgs += $containerTmp

        Write-Host "[day87] Restoring from custom-format dump..." -ForegroundColor Cyan
        docker exec $ContainerName @restoreArgs
    }

    docker exec $ContainerName rm -f $containerTmp | Out-Null
    Write-Host "[day87] DB restore complete into database '$DbName'." -ForegroundColor Green
}
finally {
    Pop-Location
}
