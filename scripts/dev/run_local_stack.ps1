param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "start",
    [string]$ComposeFile = "infra/docker/docker-compose.yml",
    [switch]$NoFrontend,
    [switch]$SkipMigrations,
    [switch]$NoBuild,
    [int]$BackendHealthTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$frontendPidFile = Join-Path $PSScriptRoot ".frontend_dev.pid"

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & docker compose -f $ComposeFile @Args
}

function Get-BackendStatusCode {
    if (Get-Command "curl.exe" -ErrorAction SilentlyContinue) {
        $rawStatus = (& curl.exe -s -o NUL -w "%{http_code}" "http://localhost:8000/api/v1/system/ping").Trim()
        if ($rawStatus -match "^\d{3}$") {
            return [int]$rawStatus
        }
    }
    return $null
}

function Wait-BackendHealthy {
    param([int]$TimeoutSeconds)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $statusCode = Get-BackendStatusCode
        if ($statusCode -eq 200) {
            Write-Host "Backend is healthy at http://localhost:8000/api/v1/system/ping" -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "Backend did not become healthy within $TimeoutSeconds seconds."
}

Push-Location $repoRoot
try {
    if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
        Write-Host "Creating .env from .env.example..." -ForegroundColor Cyan
        Copy-Item ".env.example" ".env"
    }

    switch ($Action) {
        "start" {
            Write-Host "Starting PostgreSQL, Redis, and backend..." -ForegroundColor Cyan
            if ($NoBuild) {
                Invoke-Compose up -d postgres redis backend
            }
            else {
                Invoke-Compose up --build -d postgres redis backend
            }

            if (-not $SkipMigrations) {
                Write-Host "Running database migrations..." -ForegroundColor Cyan
                Invoke-Compose run --rm backend python -m alembic -c /app/alembic.ini upgrade head
            }

            Wait-BackendHealthy -TimeoutSeconds $BackendHealthTimeoutSeconds

            if (-not $NoFrontend) {
                $frontendDir = Join-Path $repoRoot "frontend"
                $frontendCommand = @(
                    "Set-Location '$frontendDir'",
                    "if (-not (Test-Path 'node_modules')) { npm install }",
                    "npm run dev"
                ) -join "; "

                Write-Host "Starting frontend dev server in a new PowerShell window..." -ForegroundColor Cyan
                $frontendProcess = Start-Process -FilePath "powershell.exe" -ArgumentList @(
                    "-NoExit",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    $frontendCommand
                ) -PassThru

                Set-Content -Path $frontendPidFile -Value $frontendProcess.Id
            }

            Write-Host "Local stack is running." -ForegroundColor Green
            Write-Host "Backend:  http://localhost:8000/api/v1/system/ping"
            if (-not $NoFrontend) {
                Write-Host "Frontend: http://localhost:3000"
            }
        }
        "status" {
            Write-Host "Docker compose services:" -ForegroundColor Cyan
            Invoke-Compose ps

            $statusCode = Get-BackendStatusCode
            if ($statusCode -eq 200) {
                Write-Host "Backend ping status code: 200" -ForegroundColor Green
            }
            else {
                Write-Host "Backend ping endpoint is not reachable." -ForegroundColor Yellow
            }

            if (Test-Path $frontendPidFile) {
                $frontendPidText = (Get-Content $frontendPidFile | Select-Object -First 1).Trim()
                if ($frontendPidText -match "^\d+$") {
                    $frontendProcess = Get-Process -Id ([int]$frontendPidText) -ErrorAction SilentlyContinue
                    if ($null -ne $frontendProcess) {
                        Write-Host "Frontend process appears to be running (PID $frontendPidText)." -ForegroundColor Green
                    }
                    else {
                        Write-Host "Frontend PID file exists but process is not running." -ForegroundColor Yellow
                    }
                }
            }
            else {
                Write-Host "No tracked frontend process file found." -ForegroundColor Yellow
            }
        }
        "stop" {
            Write-Host "Stopping Docker compose services..." -ForegroundColor Cyan
            Invoke-Compose down

            if (Test-Path $frontendPidFile) {
                $frontendPidText = (Get-Content $frontendPidFile | Select-Object -First 1).Trim()
                if ($frontendPidText -match "^\d+$") {
                    $frontendProcess = Get-Process -Id ([int]$frontendPidText) -ErrorAction SilentlyContinue
                    if ($null -ne $frontendProcess) {
                        Write-Host "Stopping frontend process PID $frontendPidText..." -ForegroundColor Cyan
                        Stop-Process -Id ([int]$frontendPidText) -Force
                    }
                }
                Remove-Item $frontendPidFile -Force -ErrorAction SilentlyContinue
            }

            Write-Host "Local stack stopped." -ForegroundColor Green
        }
    }
}
finally {
    Pop-Location
}
