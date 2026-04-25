Param()

$ErrorActionPreference = "Stop"

Push-Location "frontend"
try {
    Write-Host "[day75] Running frontend typecheck..."
    npm run typecheck
    if ($LASTEXITCODE -ne 0) {
        throw "[day75] Frontend typecheck failed."
    }

    Write-Host "[day75] Running frontend lint..."
    npm run lint
    if ($LASTEXITCODE -ne 0) {
        throw "[day75] Frontend lint failed."
    }

    Write-Host "[day75] Running frontend build..."
    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "[day75] Frontend build failed."
    }
}
finally {
    Pop-Location
}

Write-Host "[day75] Frontend screener table checks passed."
