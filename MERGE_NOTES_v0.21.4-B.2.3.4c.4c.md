# Merge Notes — v0.21.4-B.2.3.4c.4c

## Important

This overlay was reconstructed from the retained `c.4a` audit overlay because the exact current local `c.4b` Python source was not available in the accessible file library.

The retained `c.4b` specification/results were used to reconstruct the audit-only `RS_RESTORE_10_8` behavior before adding the `c.4c` comparison-normalization and `MA120_INPUT_ONLY` work.

Therefore, do **not** blindly overwrite a newer local `strategy_integrity_audit.py` without first comparing it. The safest application path is a 3-way/manual merge against the current `D:\Projects\StockScope` working tree.

## Overlay scope

Only these implementation files are intended to change:

- `backend/app/backtest/scanner_quality/strategy_integrity_audit.py`
- `backend/tools/run_scanner_strategy_integrity_audit.py`
- `backend/tests/test_scanner_strategy_integrity_audit.py`
- `backend/tools/audit_inputs/c4c_10days.txt`

Documentation is also included.

No Production Scanner/Ranking/StrategyEngine file is included in this overlay.

## Validation in sandbox

- Python compile: PASS
- Integrity audit + pruning regression + scanner determinism regression: **28 passed**
- Real project DB replay: NOT run here because the current local repository and `market_history.db` are not mounted in this environment.

## Recommended local validation order

1. Back up or diff the current local c.4b audit files.
2. Merge the c.4c audit-only changes.
3. Run the integrity regression tests.
4. Run `inspect` and `full` using the exact same 10 dates in `backend/tools/audit_inputs/c4c_10days.txt`.
5. If same-date structural results agree, run the 80-day full audit.
6. Do not change Production MA120/RS behavior in this step.
