# StockScope v0.21.4-B.2.3.4c.4 — Implementation Notes

## Implemented

- Added an offline-only `StrategyIntegrityAuditor` for MA120 input integrity and Breakout relative-strength duplication.
- Production strategy definitions, weights, ranking, Risk, Entry/Stop/Target logic and Scanner constants are not modified.
- Part A inspects both runtime evidence and local Python source:
  - Market-history rows supplied to the Scanner snapshot path.
  - `_signal_snapshot` source-window candidates when they can be recovered from source.
  - Runtime `ma20` / `ma60` / `ma120` availability.
  - The `60일선이 120일선 위` condition in `trend_following`.
  - Simple-MA formula consistency using current MA20/MA60 before an audit-only SMA120 is allowed.
  - Breakout condition strings, metric sources, exact duplicates, duplicate metric keys, market/sector runtime equality, sector missing cases, and source-level sector→market fallback hints.
- Part B creates audit-only counterfactuals when applicable:
  - `MA120_FIXED_AUDIT`: patches only `StrategyInput.ma120`, then attempts to re-evaluate the existing strategy evaluator through the real project object graph. If re-evaluation cannot be resolved, impact is not claimed and the overall result remains conservative.
  - `RS_DEDUP_AUDIT`: removes one duplicated signal contribution only inside the audit. Exact duplicate conditions are handled directly; source-confirmed sector→market fallback duplication can remove one sector-relative-strength condition conservatively.
- Baseline, MA120-fixed and RS-dedup variants reuse the existing current candidate builder and final `rank_candidates()` policy.
- `inspect` mode records integrity evidence without future-outcome scoring.
- `full` mode also calculates 5D/10D/20D forward return, R, Target1/Stop, MFE/MAE and Top5 deltas.
- Output compaction retains only traces relevant to MA120 or RS integrity findings.
- Added CLI progress reporting so long audits do not sit silently.

## Files added

- `backend/app/backtest/scanner_quality/strategy_integrity_audit.py`
- `backend/tools/run_scanner_strategy_integrity_audit.py`
- `backend/tests/test_scanner_strategy_integrity_audit.py`

## Output files

Under `backend/runtime/quality_audit/strategy_integrity/`:

- `scanner-strategy-integrity-audit_<timestamp>.json`
- `scanner-strategy-integrity-signals_<timestamp>.csv`
- `scanner-strategy-integrity-pairs_<timestamp>.csv`
- `scanner-strategy-integrity-summary_<timestamp>.md`

## Validation performed in the overlay environment

- New c.4 integrity-audit tests: **7 passed**.
- c.1/c.2/c.3/c.3a/c.4 audit regression set: **24 passed**.
- Existing candidate-priority regression: **10 passed**.
- Python compile for the new auditor, runner and tests: **PASS**.
- Fake-store output smoke test: **PASS**, all four output files written.

## Important limitation

The complete user repository, real `market_history.db`, and the full strategy/engine object graph are not present in this sandbox. Therefore the real 10-date/80-date StockScope integration audit has **not** been claimed as passed here. The runner is designed to inspect the real project source/runtime on the user's machine and explicitly reports when an audit counterfactual cannot be re-evaluated safely.

## Recommended execution order

First run the short integrity inspection:

```powershell
python tools\run_scanner_strategy_integrity_audit.py --mode inspect --sample-size 10 --min-date-gap 3
```

Review the MA120 and Breakout-RS integrity verdicts. Then run the full temporal impact audit when a defect is confirmed or partial evidence needs impact measurement:

```powershell
python tools\run_scanner_strategy_integrity_audit.py --mode full --sample-size 80 --min-date-gap 3
```
