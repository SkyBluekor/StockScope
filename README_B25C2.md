# B.2.5-C.2 — stale backend/repro guard

This hotfix changes **diagnostics only**. It does not change Scanner ranking, Strategy, Risk, Entry, Stop, Target, or Historical Evidence.

It prevents a stale pre-B.2.5-C Scanner repro (`scanner_version < 0.21.3.7`) from being reported as PASS, and fixes legacy 7-field sort-key labeling so the last field is correctly identified as `code` instead of `tie_focus_order`.

Apply from the StockScope project root:

```powershell
python backend\tools\apply_b25c2_audit_guard.py
```

Then restart the running backend process, run Scanner `다시 분석`, and execute:

```powershell
python backend\tools\run_scanner_decision_quality_audit.py --top 5
```

Expected source scanner version: `0.21.3.7` or later.
