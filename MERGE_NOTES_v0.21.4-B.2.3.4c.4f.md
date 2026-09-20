# MERGE NOTES v0.21.4-B.2.3.4c.4f

This is the first c.4f implementation slice. It deliberately does **not** activate current OpenDART industry metadata in Production historical scoring because its point-in-time provenance is not established.

Apply over the current repository state where c.4d/c.4d.1 and c.4c are already committed.

After apply, run:

```powershell
pytest backend\tests\test_sector_rs_production_input_v0214b234c4f.py -q
pytest backend\tests\test_ma120_production_input_v0214b234c4d.py -q
pytest backend\tests\test_scanner_determinism_v0214b234b.py -q
pytest backend\tests\test_scanner_strategy_integrity_audit.py -q
```

Expected immediate property: existing Scanner results remain unchanged because no Production-safe sector input is supplied yet.

Next c.4f slice: bulk Scanner/Audit prefetch/cache layer outside BacktestEngine, followed by fixed 10D coverage audit before any 80D run.
