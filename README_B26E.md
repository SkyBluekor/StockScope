# B.2.6-E

This overlay adds the frozen-rule final holdout confirmation only. Production Scanner/Ranking/Strategy/Risk/Entry/Stop/Target files are not replaced.

Apply from the StockScope repository root:

```powershell
python .\apply_b26e_final_confirmation.py
```

Then run:

```powershell
python backend\tools\run_scanner_candidate_quality_final_confirmation.py
```
