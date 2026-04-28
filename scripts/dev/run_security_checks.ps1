param(
    [switch]$SkipNpmAudit,
    [switch]$FailOnNpmAudit
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path

Push-Location $repoRoot
try {
    Write-Host "[day88] Verifying secrets are not tracked..." -ForegroundColor Cyan
    $trackedEnv = (& git ls-files .env) | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    if ($trackedEnv.Count -gt 0) {
        throw "[day88] .env is tracked by git. Remove it from git history and keep it local only."
    }

    Write-Host "[day88] Running tracked-file secret scan..." -ForegroundColor Cyan
    python scripts/security/scan_secrets.py
    if ($LASTEXITCODE -ne 0) {
        throw "[day88] Secret scan failed. Review output."
    }

    Write-Host "[day88] Running backend dependency sanity check (pip check)..." -ForegroundColor Cyan
    python -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "[day88] pip check failed."
    }

    if (-not $SkipNpmAudit) {
        $frontendDir = Join-Path $repoRoot "frontend"
        if (Test-Path $frontendDir) {
            Write-Host "[day88] Running frontend dependency audit (npm audit --audit-level=high)..." -ForegroundColor Cyan
            Push-Location $frontendDir
            try {
                npm audit --audit-level=high
                if ($LASTEXITCODE -ne 0) {
                    if ($FailOnNpmAudit) {
                        throw "[day88] npm audit failed (high+ vulnerabilities)."
                    }
                    Write-Host "[day88] Warning: npm audit reported high+ vulnerabilities." -ForegroundColor Yellow
                }
            }
            finally {
                Pop-Location
            }
        }
    }

    Write-Host "[day88] Security checks passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
