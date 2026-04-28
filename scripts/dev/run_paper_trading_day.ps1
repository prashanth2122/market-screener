param(
    [string]$Date = "",
    [string]$BaseUrl = "http://localhost:8000",
    [string]$ApiPrefix = "/api/v1",
    [int]$Limit = 50,
    [string]$Symbol = "AAPL"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path

if (-not $Date) {
    $Date = Get-Date -Format "yyyy-MM-dd"
}

$paperDir = Join-Path $repoRoot "docs\\paper_trading"
$snapDir = Join-Path $paperDir "snapshots"
$journalFile = Join-Path $paperDir "${Date}.md"
$snapshotJson = Join-Path $snapDir "screener_${Date}.json"
$snapshotCsv = Join-Path $snapDir "screener_${Date}.csv"
$snapshotMd = Join-Path $snapDir "screener_${Date}.md"

function Ensure-Dir($path) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

function Write-FileIfMissing($path, $content) {
    if (-not (Test-Path $path)) {
        $content | Set-Content -Path $path -Encoding utf8
    }
}

Push-Location $repoRoot
try {
    Ensure-Dir $paperDir
    Ensure-Dir $snapDir

    $screenerUrl = "$BaseUrl$ApiPrefix/screener?limit=$Limit"
    Write-Host "[day91] Fetching screener snapshot: $screenerUrl" -ForegroundColor Cyan
    if (Get-Command "curl.exe" -ErrorAction SilentlyContinue) {
        & curl.exe -sS -m 15 $screenerUrl | Set-Content -Path $snapshotJson -Encoding utf8
    }
    else {
        (Invoke-WebRequest -Uri $screenerUrl -TimeoutSec 15).Content | Set-Content -Path $snapshotJson -Encoding utf8
    }

    if (-not (Test-Path $snapshotJson) -or ((Get-Item $snapshotJson).Length -lt 5)) {
        throw "[day91] Screener snapshot was empty. Ensure backend is running at $BaseUrl."
    }

    Write-Host "[day91] Converting snapshot to CSV/Markdown..." -ForegroundColor Cyan
    python scripts/paper_trading/snapshot_screener.py $snapshotJson --csv $snapshotCsv --md $snapshotMd
    if ($LASTEXITCODE -ne 0) {
        throw "[day91] snapshot conversion failed."
    }

    $template = @"
# Paper Trading Journal - $Date

## Snapshot

- Screener snapshot: `snapshots/screener_${Date}.md`
- Screener CSV: `snapshots/screener_${Date}.csv`

## Decisions (Paper)

Record the 3-10 trades you would take today (swing horizon ~1 month).

| Symbol | Direction | Entry thesis | Entry zone | Stop | Target(s) | Size (paper) | Notes |
|---|---|---|---|---|---|---|---|

## False Positives

List "top-ranked" assets you would NOT trade and why (what rule is missing?).

## False Negatives

List assets you think are attractive but the screener missed (what factor is missing?).

## Next Fixes (No code changes today unless critical)

- [ ]

"@

    Write-Host "[day91] Creating journal (if missing): $journalFile" -ForegroundColor Cyan
    Write-FileIfMissing $journalFile $template

    Write-Host "[day91] Day 91 artifacts ready under docs/paper_trading/." -ForegroundColor Green
}
finally {
    Pop-Location
}
