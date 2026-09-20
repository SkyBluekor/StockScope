# Implementation — v0.21.4-B.2.6-D

Added an offline research-only audit that reuses existing B.2.6-A/B development data and the latest B.2.6-C current-version validation result.

Files added:
- `backend/app/backtest/scanner_quality/overextension_context_audit.py`
- `backend/tools/run_scanner_overextension_context_audit.py`
- `backend/tests/test_scanner_overextension_context_audit_v0214b26d.py`

The audit does not rerun the Scanner and does not modify Production files.

The refined rule is intentionally simple and frozen:
- normal >=2-of-3 overextension remains demoted
- `trend_recovery` with exactly 2-of-3 overextension is exempt
- `trend_recovery` 3-of-3 remains demoted

Validation consumes the frozen annotations already written by B.2.6-C. Future outcome mutation cannot change refined ranking; this is covered by a focused regression test.
