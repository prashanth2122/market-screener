Param()

$ErrorActionPreference = "Stop"

Write-Host "[day60] Running sentiment + event-risk test suite..."
python -m pytest `
    backend/tests/test_sentiment_core.py `
    backend/tests/test_sentiment_scoring_job.py `
    backend/tests/test_event_risk_rules.py `
    backend/tests/test_event_risk_tagging_job.py `
    backend/tests/test_sentiment_event_risk_pipeline.py
if ($LASTEXITCODE -ne 0) {
    throw "[day60] Sentiment + event-risk test suite failed."
}
Write-Host "[day60] Sentiment + event-risk test suite completed."
