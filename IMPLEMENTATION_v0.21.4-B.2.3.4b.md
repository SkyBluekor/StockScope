# StockScope v0.21.4-B.2.3.4b — Implementation Notes

## Implemented

- Scanner VERSION bumped to `0.21.3.3` so old deep/fast decision caches are not reused.
- Production Scanner no longer selects `_deep_candidate()` based on optional local long-history row count.
- Top candidate pool always uses the canonical current-only candidate builder.
- Three-year Historical Evidence is attached after the current decision and no longer changes production rank.
- Candidate ranking key is now: current tier → missing conditions → Risk → entry gap → current strategy fit → ticker code.
- Browser Scanner session schema bumped and old Scanner decision-version sessions are rejected.
- Market Store planning now reads day-status rows in one SQLite range query instead of opening SQLite for every date/kind pair.
- Scanner planning emits per-market progress updates.
- Reproducibility JSON records the current-only decision/ranking policy plus current-window fingerprint and optional historical coverage.
- Windows `tzdata` dependency remains removed; audit timestamps use fixed KST UTC+09:00.

## Intended invariant

With the same recent Scanner input fingerprint and same analysis date, HOME and SCHOOL must produce the same current strategy, current conditions, Risk, price plan, current sort key and final rank even if their optional three-year history coverage differs.

## Validation performed in overlay environment

- Python compile: PASS for modified backend files.
- `test_scanner_determinism_v0214b234b.py`: 5 passed.
- Previous reproducibility audit regression: 2 passed.
- Existing candidate-priority regression: 10 passed.
- `scannerSession.ts` TypeScript type/syntax check: PASS.

Full-project backend/frontend test suites were not run because the complete base repository is not present in this environment.
