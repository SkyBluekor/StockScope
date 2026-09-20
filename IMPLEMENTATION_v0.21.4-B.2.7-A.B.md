# IMPLEMENTATION v0.21.4-B.2.7-A.B

Add-only research tooling:

- `backend/app/backtest/scanner_quality/entry_stability_audit.py`
- `backend/tools/run_scanner_entry_stability_audit.py`
- `backend/tests/test_scanner_entry_stability_audit_v0214b27.py`
- `backend/tools/audit_inputs/b27_entry_stability_development_53d.json`

The runner reads only the local HistoricalMarketStore. The bundled source contains candidate identity/rank/strategy and future outcomes, but every Entry Stability feature is recomputed using rows on or before each analysis date.

Feature calculations are standalone and future rows are explicitly filtered out before calculation. Research ranking consumes only same-date quartile bands and current rank.

No Production file is patched.
