# StockScope v0.21.4-B.2.7-E.1 output / READY-scope hotfix

Fixes the B.2.7-E holdout crash at the final CSV write step:

`ValueError: dict contains fields not in fieldnames`

The frozen holdout dates and VOLUME_LOW_GUARD ranking rule are unchanged. The patch fixes CSV output and also makes Top1/Top3/Top5 evaluation explicitly READY-only, so WATCH/VALIDATION rows cannot enter Entry-Stability metrics on dates with fewer than three READY candidates. Dates with no READY candidates are reported as `NO_READY` rather than an artificial tie.

## Apply

From the StockScope repository root:

```powershell
python .\apply_b27e1_csv_hotfix.py
```

Then rerun:

```powershell
python backend\tools\run_scanner_entry_stability_volume_holdout.py
```

The already-frozen `b27e_frozen_holdout_dates.txt` is reused; the holdout dates are not reselected.
