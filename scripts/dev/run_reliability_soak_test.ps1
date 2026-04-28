param(
    [int]$DurationMinutes = 60,
    [int]$IntervalSeconds = 60,
    [string]$BaseUrl = "http://localhost:8000",
    [string]$ApiPrefix = "/api/v1",
    [string]$Symbol = "AAPL",
    [string]$OutDir = "logs/soak",
    [switch]$StartStack,
    [switch]$FailFast,
    [switch]$NoWriteOps
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outPath = Join-Path $repoRoot $OutDir
$logFile = Join-Path $outPath "soak_${timestamp}.jsonl"

function Get-BackendStatusCode {
    $pingUrl = "$BaseUrl$ApiPrefix/system/ping"
    if (Get-Command "curl.exe" -ErrorAction SilentlyContinue) {
        $rawStatus = (& curl.exe -s -o NUL -w "%{http_code}" $pingUrl).Trim()
        if ($rawStatus -match "^\d{3}$") {
            return [int]$rawStatus
        }
    }
    try {
        $resp = Invoke-WebRequest -Uri $pingUrl -TimeoutSec 5
        return [int]$resp.StatusCode
    } catch {
        return $null
    }
}

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Url,
        [hashtable]$Headers = @{},
        [string]$BodyJson = $null
    )

    $requestId = "soak-$([Guid]::NewGuid().ToString('N'))"
    $Headers["X-Request-ID"] = $requestId

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if (Get-Command "curl.exe" -ErrorAction SilentlyContinue) {
            # Use curl's explicit http_code formatter; no response body needed for soak.
            $curlArgs = @("-sS", "-m", "10", "-X", $Method, "-w", "%{http_code}", "-o", "NUL")
            foreach ($key in $Headers.Keys) {
                $curlArgs += @("-H", "${key}: $($Headers[$key])")
            }
            if ($BodyJson) {
                $curlArgs += @("-H", "Content-Type: application/json", "--data", $BodyJson)
            }
            $curlArgs += $Url

            $statusCode = 0
            $statusText = ((& curl.exe @curlArgs 2>$null) -join "").Trim()
            if ($statusText -match "^\\d{3}$") { $statusCode = [int]$statusText }

            return @{
                ok = ($statusCode -ge 200 -and $statusCode -lt 300)
                status = $statusCode
                body = ""
                request_id = $requestId
            }
        }

        $params = @{
            Uri = $Url
            Method = $Method
            Headers = $Headers
            TimeoutSec = 10
        }
        if ($BodyJson) {
            $params["ContentType"] = "application/json"
            $params["Body"] = $BodyJson
        }
        $resp = Invoke-WebRequest @params
        return @{
            ok = ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
            status = [int]$resp.StatusCode
            body = $resp.Content
            request_id = $requestId
        }
    }
    finally {
        $stopwatch.Stop()
    }
}

function Write-Jsonl {
    param([hashtable]$Obj)
    $Obj["ts"] = (Get-Date).ToString("o")
    ($Obj | ConvertTo-Json -Compress) | Add-Content -Path $logFile -Encoding utf8
}

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $outPath | Out-Null

    if ($StartStack) {
        Write-Host "[day89] Starting local stack..." -ForegroundColor Cyan
        powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action start | Out-Null
    }

    # Preflight reachability to avoid generating a useless log when the stack isn't running.
    $statusCode = Get-BackendStatusCode
    if ($statusCode -ne 200) {
        if ($StartStack) {
            $statusCode = Get-BackendStatusCode
        }
        if ($statusCode -ne 200) {
            throw "[day89] Backend is not reachable at $BaseUrl$ApiPrefix/system/ping. Start the stack or pass -StartStack."
        }
    }

    $deadline = (Get-Date).AddMinutes([Math]::Max(1, $DurationMinutes))
    $total = 0
    $ok = 0
    $fail = 0

    Write-Host "[day89] Soak running for $DurationMinutes minutes (interval $IntervalSeconds sec). Log: $logFile" -ForegroundColor Cyan

    while ((Get-Date) -lt $deadline) {
        $iterationStarted = Get-Date
        $total += 1

        $requests = @(
            @{ name = "ping"; method = "GET"; url = "$BaseUrl$ApiPrefix/system/ping" },
            @{ name = "health"; method = "GET"; url = "$BaseUrl/health" },
            @{ name = "screener"; method = "GET"; url = "$BaseUrl$ApiPrefix/screener?limit=50" },
            @{ name = "asset_detail"; method = "GET"; url = "$BaseUrl$ApiPrefix/assets/${Symbol}?price_limit=50&news_limit=10" }
        )

        if (-not $NoWriteOps) {
            $requests += @(
                @{ name = "watchlists_list"; method = "GET"; url = "$BaseUrl$ApiPrefix/watchlists" },
                @{ name = "alert_history"; method = "GET"; url = "$BaseUrl$ApiPrefix/alert-history?limit=20" }
            )
        }

        foreach ($req in $requests) {
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $result = $null
            $err = $null
            try {
                $result = Invoke-JsonRequest -Method $req.method -Url $req.url
            }
            catch {
                $err = $_.Exception.Message
            }
            finally {
                $sw.Stop()
            }

            $entry = @{
                kind = "http_check"
                name = $req.name
                method = $req.method
                url = $req.url
                duration_ms = $sw.Elapsed.TotalMilliseconds
            }

            if ($err) {
                $fail += 1
                $entry["ok"] = $false
                $entry["status"] = $null
                $entry["error"] = $err
                if ($FailFast) {
                    Write-Jsonl -Obj $entry
                    throw "[day89] FailFast hit on $($req.name): $err"
                }
            }
            else {
                if ($result.ok) { $ok += 1 } else { $fail += 1 }
                $entry["ok"] = [bool]$result.ok
                $entry["status"] = $result.status
                $entry["request_id"] = $result.request_id
                if ($FailFast -and (-not $result.ok)) {
                    Write-Jsonl -Obj $entry
                    throw "[day89] FailFast hit on $($req.name): status=$($result.status)"
                }
            }

            Write-Jsonl -Obj $entry
        }

        $elapsed = (Get-Date) - $iterationStarted
        $sleepSeconds = [Math]::Max(0, $IntervalSeconds - [int][Math]::Ceiling($elapsed.TotalSeconds))
        if ($sleepSeconds -gt 0) {
            Start-Sleep -Seconds $sleepSeconds
        }
    }

    $summary = @{
        kind = "summary"
        duration_minutes = $DurationMinutes
        interval_seconds = $IntervalSeconds
        total_iterations = $total
        request_ok = $ok
        request_fail = $fail
        log_file = $logFile
    }
    Write-Jsonl -Obj $summary

    Write-Host "[day89] Soak complete. ok=$ok fail=$fail log=$logFile" -ForegroundColor Green
}
finally {
    Pop-Location
}
