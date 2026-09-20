# B.2.7-C overlay

From the StockScope repository root:

```powershell
python .\apply_b27c_entry_stability_validation.py
python backend\tools\run_scanner_entry_stability_validation.py
```

Prerequisite: B.2.7-A/B must already be installed because C reuses `compute_entry_stability_features()`.
