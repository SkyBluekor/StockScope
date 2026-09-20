# B.2.7-E

Apply from the StockScope repository root:

```powershell
python .\apply_b27e_volume_holdout.py
```

Then run:

```powershell
python backend\tools\run_scanner_entry_stability_volume_holdout.py
```

Do not modify the generated frozen holdout dates after outcomes are observed. If the verdict is not `PROMOTE_VOLUME_LOW_GUARD`, do not run B.2.7-F and do not retune Q25 on this holdout.
