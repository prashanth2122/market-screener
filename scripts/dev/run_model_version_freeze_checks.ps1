Param()

$ErrorActionPreference = "Stop"

Write-Host "[day97] Running model version freeze checks..." -ForegroundColor Cyan
python -m pytest -q backend/tests/test_model_version_changelog.py
if ($LASTEXITCODE -ne 0) {
    throw "[day97] Model version freeze checks failed."
}
Write-Host "[day97] Model version freeze checks passed." -ForegroundColor Green
