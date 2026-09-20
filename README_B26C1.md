# StockScope v0.21.4-B.2.6-C.1 — Date Parser Hotfix

Fixes the B.2.6-C evaluation-date parser bug where a comma inside a comment line was expanded before the comment was discarded, causing text such as `held fixed for current-version comparison.` to be parsed as an ISO date.

Changes only:
- `backend/tools/run_scanner_candidate_quality_validation.py`
- one focused regression test

Production Scanner/Ranking/Strategy/Risk/Entry/Target logic is unchanged.
