param(
    [string]$Date = "",
    [int]$Top = 10
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path

if (-not $Date) {
    $Date = Get-Date -Format "yyyy-MM-dd"
}

$paperDir = Join-Path $repoRoot "docs\\paper_trading"
$snapDir = Join-Path $paperDir "snapshots"
$reviewDir = Join-Path $paperDir "reviews"

$snapshotJson = Join-Path $snapDir "screener_${Date}.json"
$snapshotMd = Join-Path $snapDir "screener_${Date}.md"
$journalFile = Join-Path $paperDir "${Date}.md"
$reviewFile = Join-Path $reviewDir "review_${Date}.md"

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
    Ensure-Dir $reviewDir

    if (-not (Test-Path $snapshotJson)) {
        throw "[day92] Missing snapshot: $snapshotJson. Run Day 91 first."
    }

    Write-Host "[day92] Generating snapshot summary..." -ForegroundColor Cyan
    python scripts/paper_trading/analyze_snapshot.py $snapshotJson --out $reviewFile --top $Top
    if ($LASTEXITCODE -ne 0) {
        throw "[day92] snapshot analyzer failed."
    }

    $append = @"
# Paper Trading Review - $Date

Links:
- Journal: `../$Date.md`
- Snapshot table: `../snapshots/screener_${Date}.md`

## What I Traded (Paper)

Copy the trades you recorded in the journal and add outcome notes.

| Symbol | Direction | Outcome (win/loss/flat/open) | Notes |
|---|---|---|---|

## False Positives (Top-ranked but NO trade)

| Symbol | Why I passed | Missing rule? | Fix idea |
|---|---|---|---|

## False Negatives (Good but missed/low-ranked)

| Symbol | Why it’s good | What screener missed | Fix idea |
|---|---|---|---|

## Decisions (Day 92)

- [ ] Top 3 false-positive patterns
- [ ] Top 3 false-negative patterns
- [ ] One fix to implement later (do not change weights today)

"@

    Add-Content -Path $reviewFile -Value $append -Encoding utf8
    Write-Host "[day92] Review file ready: $reviewFile" -ForegroundColor Green

    if (-not (Test-Path $journalFile)) {
        Write-Host "[day92] Note: journal file is missing: $journalFile" -ForegroundColor Yellow
    }
    if (-not (Test-Path $snapshotMd)) {
        Write-Host "[day92] Note: snapshot markdown table is missing: $snapshotMd" -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}
