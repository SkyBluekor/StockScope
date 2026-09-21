# TRACK.1.10.1 — Embedded Scanner in Stock Tracking

Scope is intentionally narrow: make the existing StockScope Scanner runnable from the Stock Tracking page without changing Scanner production logic.

## Changes

- Adds `EmbeddedScanner.tsx` to the Stock Tracking page.
- Uses the existing Scanner job APIs (`createScannerJob`, `fetchBacktestJob`, `cancelBacktestJob`).
- Uses the existing Scanner progress contract and shared reactive `scannerSession` store.
- Runs in-place: market scope → progress → completed recommendations, with no navigation required.
- Completed results are committed to the same Scanner session used by the main Stock Finder page.
- Main `ScannerPanel` subscribes to shared session updates so a result completed from Stock Tracking is visible even if the user navigates to the main Scanner while the job is still running.
- RecommendationTracking reads both `candidates` and `more_candidates`; it does not truncate in the Tracking UI.
- Keeps manual stock add and tracked-record management unchanged.

## Explicit non-scope

- No Scanner ranking/strategy/risk/entry/stop/target changes.
- No change to Scanner `candidate_limit` production request (still 5, matching the existing main Scanner contract).
- No backend changes.
- No Historical Validation changes.

## Apply

Run from the StockScope project root:

```powershell
python .\apply_track1101_embedded_scanner.py
```

The script backs up touched files in memory and restores them if source tests or the frontend production build fails.
