# SIM.0 Quick Run

From the StockScope repository root:

```powershell
python .\apply_sim0_production_baseline.py
python backend\tools\freeze_scanner_production_baseline.py
python backend\tools\verify_scanner_production_baseline.py
```

Expected freeze status: `BASELINE_FROZEN`.
Expected verify status immediately afterward: `BASELINE_VALID`.

Do not edit or overwrite an existing baseline manifest. A real Production Scanner change must receive a new Scanner version and a new baseline manifest.
