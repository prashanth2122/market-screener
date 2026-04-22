# 100 Day Plan (Elite Personal Build)

## Plan Objective

In 100 days, ship a stable personal market screener with reliable data, explainable scoring, and actionable alerts.

## Working Rules

- Work 90-120 focused minutes daily minimum.
- Commit code or docs every day.
- Keep one running changelog of decisions and results.
- Track signal precision weekly with manual review notes.

## Days 1-10 Sprint (Detailed Execution)

1. Day 1: Define success and operating constraints.
- Tasks: lock product purpose, user flow, day-100 success statement, zero-budget rule.
- Output: one-page success brief in `docs/`.
- Done when: you can explain in 60 seconds what this product does and what it will not do.

2. Day 2: Lock symbol universe and segmentation.
- Tasks: finalize the 150-symbol universe (S&P 50 + NSE 50 + Crypto 50), store as versioned list.
- Output: `config/symbols_v1.json`.
- Done when: every symbol has asset type, exchange, and quote currency.

3. Day 3: Freeze provider and failover matrix.
- Tasks: document provider order and fallback behavior per asset class.
- Output: `docs/provider_matrix.md`.
- Done when: each asset class has primary, backup, and timeout/retry policy.

4. Day 4: Create production-ready repository layout.
- Tasks: create module folders for backend, frontend, infra, config, docs, scripts.
- Output: clean project tree with placeholder README per major module.
- Done when: structure supports independent work without path confusion.

5. Day 5: Define environment contract.
- Tasks: create `.env.example` with required variables for APIs, DB, cache, auth, telegram.
- Output: `.env.example` + `docs/env_reference.md`.
- Done when: a fresh machine can be configured using docs only.

6. Day 6: Draw architecture and data flow.
- Tasks: define services, data flow, failure points, and recovery paths.
- Output: architecture diagram and short runbook notes in `docs/`.
- Done when: ingestion-to-alert flow is clear end-to-end.

7. Day 7: Freeze MVP vs v1 boundaries.
- Tasks: mark must-have, should-have, and later features.
- Output: `docs/scope_matrix.md`.
- Done when: any new feature request can be accepted/rejected quickly.

8. Day 8: Convert scope into acceptance criteria.
- Tasks: write testable requirements for ingestion freshness, alert timing, and dashboard utility.
- Output: acceptance checklist appended to implementation spec.
- Done when: each requirement has an objective pass/fail check.

9. Day 9: Set engineering standards.
- Tasks: choose formatter, linter, naming rules, commit conventions, branch rules.
- Output: `CONTRIBUTING.md` with standards.
- Done when: code quality expectations are explicit and repeatable.

10. Day 10: Automate local quality gates.
- Tasks: configure pre-commit hooks for format, lint, and basic static checks.
- Output: `.pre-commit-config.yaml` and verified local hook run.
- Done when: commits are blocked on formatting/lint failures.

## Day-by-Day Execution

1. Define success criteria and personal workflow goals.
2. Finalize asset universe (symbols, exchanges, crypto pairs).
3. Decide primary and backup providers per asset class.
4. Create repository structure and baseline README cleanup.
5. Add `.env.example` with all required secrets.
6. Create architecture diagram and module boundaries.
7. Define MVP and v1 scope boundaries clearly.
8. Write implementation spec and acceptance criteria.
9. Set coding standards and linting rules.
10. Configure pre-commit hooks and formatting.

11. Initialize backend project skeleton.
12. Initialize frontend project skeleton.
13. Add Docker Compose for DB, cache, backend.
14. Set up PostgreSQL locally and confirm connectivity.
15. Create initial DB migration framework.
16. Add base tables: assets, prices, jobs, provider health.
17. Build config management module.
18. Add structured logging setup.
19. Add health-check endpoint.
20. Create first CI workflow (lint + tests).

21. Implement provider client: Alpha Vantage wrapper.
22. Implement provider client: Finnhub wrapper.
23. Implement retry and timeout policy for clients.
24. Implement rate limit guard with quota counters.
25. Build symbol metadata ingestion job.
26. Build OHLCV ingestion job for equity symbols.
27. Persist ingestion metadata for audit trail.
28. Add idempotency checks for repeated pulls.
29. Add ingestion failure table and retry workflow.
30. Validate 7-day historical backfill for 20 symbols.

31. Implement CoinGecko client for crypto.
32. Add crypto OHLCV ingestion pipeline.
33. Add commodities and forex ingestion source.
34. Normalize all price payloads to common schema.
35. Add trading calendar handling for market closures.
36. Add timezone normalization to UTC storage.
37. Add freshness monitor job for watchlist symbols.
38. Add provider latency and success dashboards.
39. Stress test ingestion with 100 symbols.
40. Refactor ingestion for clean adapter interfaces.

41. Integrate TA calculation library.
42. Implement MA50, MA200, RSI14 calculations.
43. Implement MACD and signal line calculations.
44. Implement ATR and Bollinger Bands calculations.
45. Add indicator snapshot table and writes.
46. Implement trend regime classification logic.
47. Implement breakout detection logic.
48. Implement relative volume calculation.
49. Add indicator unit tests with known fixtures.
50. Validate indicator outputs against reference values.

51. Design fundamentals ingestion schema.
52. Implement fundamentals client and snapshot pull.
53. Compute Piotroski F-score function.
54. Compute Altman Z-score function.
55. Add growth metrics computation (EPS and revenue).
56. Add fundamentals quality normalization (0-100).
57. Implement news API client and article storage.
58. Implement sentiment scoring pipeline.
59. Implement event risk tagging rules.
60. Add tests for sentiment and risk tagging.

61. Define score weights and factor transforms.
62. Implement composite score engine v1.
63. Add score explanation payload per asset.
64. Create signal mapping rules (Strong Buy, Buy, Watch, Avoid).
65. Add score and signal history tables.
66. Backfill scores for recent 90 days.
67. Validate score stability on sample assets.
68. Add rule engine for alerts.
69. Add email alert channel integration.
70. Add Telegram or Slack alert channel integration.

71. Build screener API endpoint with filters.
72. Build asset detail API endpoint.
73. Build watchlist CRUD endpoints.
74. Build alert history API endpoint.
75. Create frontend screener table view.
76. Add filters, sorting, and pagination in UI.
77. Build symbol detail page with chart overlays.
78. Add news and sentiment panel to detail page.
79. Add score explanation panel in UI.
80. Add alert preferences and rule toggles in UI.

81. Add end-to-end tests for core flows.
82. Add ingestion replay tool for failed windows.
83. Add dead-letter queue handling for bad payloads.
84. Add API caching for high-frequency dashboard queries.
85. Add performance profiling for slow DB queries.
86. Tune indexes for screener and detail endpoints.
87. Add backup and restore scripts for DB.
88. Add security checks for secrets and dependencies.
89. Run 7-day reliability soak test.
90. Fix reliability and performance defects from soak test.

91. Start 10-day paper-trading validation loop.
92. Review false positives and false negatives.
93. Adjust scoring transforms (not weights yet).
94. Tune alert thresholds and cooldown windows.
95. Add daily summary digest report.
96. Finalize personal playbook for using signals.
97. Freeze v1 model version and changelog.
98. Write runbook for maintenance and failures.
99. Prepare launch checklist and final QA pass.
100. Launch personal v1 and begin weekly improvement cycle.

## Weekly Review Template

Every 7 days, review:
- ingestion reliability
- data freshness
- alert usefulness
- score quality vs your manual judgment
- top 3 fixes for next week

## Post-Day-100 Operating Cadence

- Weekly: threshold tuning and provider quality review
- Monthly: model version update and backtest sanity check
- Quarterly: architecture cleanup and feature pruning
