# IMPLEMENTATION v0.21.4-B.2.3.4c.3
## Strategy Search Audit — Top3 vs All

### Scope
Implemented the audit-only Top3-vs-All strategy search experiment defined in the workspec.
Production Scanner defaults, ranking, Risk, Entry/Stop/Target, Quick18 and Market160 were not changed.

### Added
- `backend/app/backtest/scanner_quality/strategy_search_audit.py`
  - Reuses the production quick pool (Market160 / Quick18) so stock selection stays fixed.
  - Evaluates the same selected stocks under `BASELINE_TOP3` and `ALL_STRATEGIES`.
  - Reuses production snapshot, condition-state, current-readiness, Risk and entry-risk guide helpers.
  - Detects selected strategies whose initial strategy rank is outside Top3.
  - Records strategy changes, candidate-state/Risk/missing-condition changes, Top5 changes and paired outcomes.
  - Aggregates 5D/10D/20D return/R/Target1/Stop metrics, trimmed statistics and runtime cost.
  - Produces one of `KEEP_TOP3 / CONSIDER_ALL / CONSIDER_EXPANDED_K / INCONCLUSIVE`.
  - Compacts persistent JSON to keep detailed strategy traces only for changed/outside-Top3/parity-mismatch symbols.

- `backend/tools/run_scanner_strategy_audit.py`
  - Offline-only CLI runner. Any KRX download attempt raises immediately.
  - Reuses B.2.3.4c.2 temporal spread date sampling.
  - Default: 80 spread dates, min trading-date gap 3.
  - Prints per-date progress including strategy changes and outside-Top3 selections.

- `backend/tests/test_scanner_strategy_audit.py`
  - Variant isolation / fixed quick pool.
  - Outside-Top3 strategy detection.
  - Deterministic same-input result.
  - Future-only data mutation cannot change strategy selection.
  - Runtime/verdict aggregation fixture.

- `backend/app/backtest/scanner_quality/__init__.py`
  - Exports the new audit API while retaining existing pruning audit exports.

### Output directory
`backend/runtime/quality_audit/strategy_search/`

Generated files:
- `scanner-strategy-audit_<timestamp>.json`
- `scanner-strategy-signals_<timestamp>.csv`
- `scanner-strategy-pairs_<timestamp>.csv`
- `scanner-strategy-summary_<timestamp>.md`

### Recommended command
From `D:\Projects\StockScope\backend` with `.venv` active:

```powershell
python tools\run_scanner_strategy_audit.py --sample-size 80 --min-date-gap 3
```

Smoke test:

```powershell
python tools\run_scanner_strategy_audit.py --sample-size 20
```

### Verification performed in the implementation workspace
- Python compile: PASS
- Strategy search audit tests: 4/4 PASS
- Existing B.2.3.4c.2 pruning audit tests + new tests: 11/11 PASS
- Candidate Priority regression tests: 10/10 PASS

Total executed test assertions by pytest files: 21 PASS.

### Not verified here
The implementation environment does not contain the user's real `market_history.db` or complete production repository, so the real 80-date integration audit must be run on the user's StockScope project.

### Prerequisite
Apply on top of `v0.21.4-B.2.3.4c.2` (or a project already containing its `scanner_quality/early_pruning_audit.py` and temporal sampling helpers).
