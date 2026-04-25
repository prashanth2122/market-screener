Param(
    [int]$SinceHours = 24,
    [int]$UntilHours = 0,
    [int]$Limit = 200,
    [string]$JobName = "",
    [string]$Statuses = ""
)

$ErrorActionPreference = "Stop"

Write-Host "[day82] Running ingestion failure replay..."

$jobNameArg = ""
if ($JobName -and $JobName.Trim() -ne "") {
    $jobNameArg = "job_name='$($JobName.Trim())',"
}

$statusesArg = ""
if ($Statuses -and $Statuses.Trim() -ne "") {
    $set = $Statuses.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" } | ForEach-Object { "'$_'" }
    if ($set.Count -gt 0) {
        $statusesArg = "statuses={$(($set -join ","))},"
    }
}

$py = @"
from market_screener.jobs.ingestion_replay import run_ingestion_failure_replay
result = run_ingestion_failure_replay(
    since_hours=$SinceHours,
    until_hours=$UntilHours,
    limit=$Limit,
    $jobNameArg
    $statusesArg
)
print(result)
"@

python -c $py
if ($LASTEXITCODE -ne 0) {
    throw "[day82] Ingestion failure replay failed."
}
Write-Host "[day82] Ingestion failure replay completed."
