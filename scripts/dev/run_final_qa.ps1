param(
    [switch]$SkipFrontend,
    [switch]$SkipNpmAudit
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path

function Run-Step {
    param([string]$Name, [scriptblock]$Block)
    Write-Host "[qa] $Name" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) {
        throw "[qa] Failed: $Name"
    }
}

Push-Location $repoRoot
try {
    Run-Step "Model version freeze" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_model_version_freeze_checks.ps1 }
    Run-Step "API index smoke" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_api_index_smoke_tests.ps1 }
    Run-Step "DLQ tests" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_dead_letter_queue_tests.ps1 }
    Run-Step "API cache tests" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_api_cache_tests.ps1 }
    Run-Step "Slow query profiler tests" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_slow_query_profiler_tests.ps1 }
    Run-Step "Alert gating tests" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_alert_threshold_cooldown_tests.ps1 }
    Run-Step "Daily digest tests" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_daily_digest_tests.ps1 }

    if ($SkipNpmAudit) {
        Run-Step "Security checks (skip npm audit)" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_security_checks.ps1 -SkipNpmAudit }
    }
    else {
        Run-Step "Security checks" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_security_checks.ps1 }
    }

    if (-not $SkipFrontend) {
        Run-Step "Frontend checks" { powershell -ExecutionPolicy Bypass -File scripts/dev/run_frontend_screener_table_checks.ps1 }
    }

    Write-Host "[qa] Final QA passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
