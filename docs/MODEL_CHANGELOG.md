# Model Changelog

This file is the source of truth for the score model version history.

Rules:
- Every change to scoring transforms, scoring weights, or signal mapping must bump `SCORE_MODEL_VERSION`.
- Every bump must add an entry here describing what changed and why.
- Keep changes small and measurable; do not change weights during validation loops.

## v1.0.1 (2026-04-28)

Type: transform change (no weight changes)

Changes:
- Confidence shaping: added a confidence floor + power curve to reduce overreaction to low-confidence technical regimes/signals.
- Weighted-sentiment fallback mapping changed from linear to logistic to stabilize mid-range scores and bound extremes.

Notes:
- Component weights remain unchanged: technical 0.45, fundamentals 0.35, sentiment/risk 0.20.

## v1.0.0 (2026-04-22)

Type: baseline

Changes:
- Initial composite score v1 with 3 components (technical, fundamentals, sentiment/risk).
- Initial signal mapping gates and score explanation payload.
