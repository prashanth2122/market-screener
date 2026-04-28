param(
    [Parameter(Mandatory = $true)]
    [string]$LogFile,
    [string]$OutDir = "logs/soak"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$resolvedLog = (Resolve-Path $LogFile).Path
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outPath = Join-Path $repoRoot $OutDir
$reportFile = Join-Path $outPath "soak_report_${timestamp}.md"

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $outPath | Out-Null
    python scripts/soak/analyze_soak.py $resolvedLog --out $reportFile
    Write-Host "[day90] Soak report written: $reportFile" -ForegroundColor Green
}
finally {
    Pop-Location
}
