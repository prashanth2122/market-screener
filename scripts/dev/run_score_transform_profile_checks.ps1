Param()

$ErrorActionPreference = "Stop"

Write-Host "[day93] Running score transform profile checks..." -ForegroundColor Cyan
python -m pytest -q backend/tests/test_score_factor_transforms.py backend/tests/test_composite_score_engine.py
if ($LASTEXITCODE -ne 0) {
    throw "[day93] Score transform profile checks failed."
}
Write-Host "[day93] Score transform profile checks passed." -ForegroundColor Green
