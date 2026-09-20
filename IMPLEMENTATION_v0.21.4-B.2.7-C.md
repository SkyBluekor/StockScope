# Implementation — v0.21.4-B.2.7-C

This overlay is additive-only.

Added files:
- `backend/app/backtest/scanner_quality/entry_stability_validation.py`
- `backend/tools/run_scanner_entry_stability_validation.py`
- `backend/tests/test_scanner_entry_stability_validation_v0214b27c.py`
- `backend/tools/audit_inputs/b27c_validation_dates.txt`

Safety properties:
- Scanner version is hard-gated to `0.21.3.7`.
- Entry Stability features use rows on/before D only.
- CURRENT and all three rule rankings are frozen before D+1 future rows are read.
- Rules only reorder READY slots; WATCH/VALIDATION positions are immutable.
- Production files are not patched.
- Same-date READY Q25/Q75 is reused without numeric threshold tuning.
