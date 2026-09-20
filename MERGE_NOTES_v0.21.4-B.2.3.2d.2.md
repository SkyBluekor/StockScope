# MERGE NOTES v0.21.4-B.2.3.2d.2

Apply after B.2.3.2d and B.2.3.2d.1.

Changed code:
- `backend/app/backtest/entry_risk_guide.py`
- `frontend/src/components/ScannerPanel.tsx`
- `frontend/src/components/EntryRiskGuideCard.tsx`
- focused regression test

No RiskEngine/Target1/Target2/Strategy/Ranking/Scanner-version change.

After applying:
```powershell
pytest backend\tests\test_target1_cap_metadata_wiring_v0214b232d2.py -q
npm --prefix frontend run build
```

Then re-run Scanner once (or clear/recreate the Scanner session) and inspect Hanmi Science detail.
