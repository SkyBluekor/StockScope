# MERGE NOTES v0.21.4-B.2.3.4c.4f.3

Apply after c.4f.2.

This phase does not activate Sector RS in Production. With current OpenDART metadata, Engine temporal gating keeps Production sector input `None`; the real sector value is exposed only in audit metadata.

Recommended verification:

```powershell
pytest backend\tests\test_sector_rs_audit_coverage_v0214b234c4f3.py -q
pytest backend\tests\test_sector_rs_prefetch_v0214b234c4f2.py -q
pytest backend\tests\test_sector_rs_production_input_v0214b234c4f.py -q
pytest backend\tests\test_ma120_production_input_v0214b234c4d.py -q
pytest backend\tests\test_scanner_determinism_v0214b234b.py -q
pytest backend\tests\test_scanner_strategy_integrity_audit.py -q
```

Then run fixed 10D audit:

```powershell
python backend\tools\run_scanner_strategy_integrity_audit.py `
  --mode inspect `
  --evaluation-dates-file backend\tools\audit_inputs\c4c_10days.txt `
  --sector-rs-audit-live
```

Expected policy state: `STATIC_CURRENT`, `production_activation_allowed=False`.
