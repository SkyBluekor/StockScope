# StockScope B.2.7-A/B Entry Stability Discovery

From the StockScope project root:

```powershell
python .\apply_b27_entry_stability_audit.py
python backend\tools\run_scanner_entry_stability_audit.py
```

Outputs are written to:

`backend/runtime/quality_audit/entry_stability/`

Expected final console shape:

```text
B.2.7-A/B: <VERDICT> | best=<feature:band> | Top3 T1 ... -> ... | Stop ... -> ... | production_changed=False
```

This step is discovery-only. Do not treat a promising development smoke result as Production validation.
