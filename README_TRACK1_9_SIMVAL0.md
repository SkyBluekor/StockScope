# StockScope TRACK.1.9 + SIM.VAL.0

This overlay fixes the product/UX integrity issues found after TRACK.1 Phase 2.

## Included

- Reactive Scanner session store (`useSyncExternalStore`) with schema-versioned persistence.
- Synchronous Scanner result commit before navigation.
- `추천 추적` -> `종목 추적` with Scanner recommendations, direct stock add, and tracking list.
- Server-owned SCANNER/MANUAL provenance endpoints.
- Tracking DB v3 migration: snapshot schema/hash, closed market date, frozen closed records.
- Manual tracking reference price from latest confirmed Market Store close.
- Historical Validation foundation: 6m/1y/2y presets, YYYY-MM custom range, actual trading-day preview, 60-day minimum policy.
- Legacy Simulation portfolios preserved and listed read-only; no localStorage auto-activation.
- Existing SIM.1~SIM.3 API/data remain in place for compatibility, but the new validation UI does not pretend the old manual fill engine is the new strategy validator.

## Apply

From the StockScope project root:

```powershell
python .\apply_track1_integrity_simval0.py
```

The script backs up changed files in memory and rolls them back if focused pytest or frontend build fails. Scanner production baseline verification is report-only because the known mismatch predates this patch.
