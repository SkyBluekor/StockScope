# StockScope TRACK.1 Phase 2 — Recommendation Performance Tracking

## Scope

This overlay continues from TRACK.1 Phase 1.

Implemented:

- `TRACK.1.3` Historical Market Store performance refresh
- `TRACK.1.4` recommendation performance engine
- `TRACK.1.5` bulk/single refresh API
- `TRACK.1.6` performance-first recommendation tracking UI
- `TRACK.1.7` 5D / 10D / 20D and Entry / Stop / Target touch events
- small terminology cleanup in the historical strategy validation screen

## Data rules

- Recommendation day D is never used as post-recommendation performance.
- Performance begins on D+1 trading day.
- 5D / 10D / 20D are market trading-day horizons, not calendar days.
- Price history remains sourced from the existing Historical Market Store.
- Missing stock bars are not converted to 0.
- Scanner snapshot data remains immutable during refresh.
- Stop/Target touches are observations only; this feature does not claim execution order or fills.
- CLOSED recommendations are excluded from bulk refresh.

## Apply

From the StockScope project root:

```powershell
python .\apply_track1_phase2.py
```

The apply script runs focused regression tests and the frontend production build. On failure, Phase 2 file changes are rolled back.

The existing Scanner production-baseline mismatch is report-only because this overlay does not modify Scanner production files.
