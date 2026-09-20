# B.2.6-D

Apply from the StockScope project root, then run:

```powershell
python backend\tools\run_scanner_overextension_context_audit.py
```

The runner auto-selects the latest B.2.6-C JSON from:

`backend/runtime/quality_audit/candidate_quality_validation/`

You can override it with:

```powershell
python backend\tools\run_scanner_overextension_context_audit.py --current-validation <path-to-json>
```
