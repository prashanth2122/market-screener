param(
    [switch]$SkipFrontend,
    [switch]$SkipNpmAudit,
    [switch]$NoStartStack
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path

Push-Location $repoRoot
try {
    Write-Host "[day100] Running final QA..." -ForegroundColor Cyan
    if ($SkipFrontend -and $SkipNpmAudit) {
        powershell -ExecutionPolicy Bypass -File scripts/dev/run_final_qa.ps1 -SkipFrontend -SkipNpmAudit
    }
    elseif ($SkipFrontend) {
        powershell -ExecutionPolicy Bypass -File scripts/dev/run_final_qa.ps1 -SkipFrontend
    }
    elseif ($SkipNpmAudit) {
        powershell -ExecutionPolicy Bypass -File scripts/dev/run_final_qa.ps1 -SkipNpmAudit
    }
    else {
        powershell -ExecutionPolicy Bypass -File scripts/dev/run_final_qa.ps1
    }

    if (-not $NoStartStack) {
        Write-Host "[day100] Starting local stack..." -ForegroundColor Cyan
        powershell -ExecutionPolicy Bypass -File scripts/dev/run_local_stack.ps1 -Action start | Out-Null
    }

    Write-Host "[day100] Launch complete. Next actions:" -ForegroundColor Green
    Write-Host "  - Paper-trading day: powershell -ExecutionPolicy Bypass -File scripts/dev/run_paper_trading_day.ps1" -ForegroundColor Green
    Write-Host "  - Review:           powershell -ExecutionPolicy Bypass -File scripts/dev/run_paper_trading_review.ps1" -ForegroundColor Green
    Write-Host "  - Backup DB:        powershell -ExecutionPolicy Bypass -File scripts/dev/run_db_backup.ps1" -ForegroundColor Green
}
finally {
    Pop-Location
}
