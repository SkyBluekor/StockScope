# SIM.0 Implementation Notes

Added only reproducibility tooling:

- `backend/app/baseline/scanner_production_baseline.py`
- `backend/tools/freeze_scanner_production_baseline.py`
- `backend/tools/verify_scanner_production_baseline.py`
- `backend/tests/test_scanner_production_baseline_sim0.py`
- `backend/runtime/baseline/README.md`

No existing Production Scanner source is part of this payload.

After applying, run the freeze command exactly once. It refuses to overwrite an existing manifest. Then run verification; it reports modified, missing, or newly discovered Production dependencies individually.
