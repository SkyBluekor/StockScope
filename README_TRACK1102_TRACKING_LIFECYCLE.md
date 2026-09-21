# TRACK.1.10.2 — Tracking Record UX & Lifecycle

This overlay completes the user-facing lifecycle after `추적 시작` without changing Scanner production logic, Tracking DB schema, or Historical Validation.

## Changes

- Scanner/manual additions update the tracking list immediately from the API response.
- Scanner candidate buttons distinguish `추적 중` from `추적 종료됨`.
- Tracking list filters show counts and ACTIVE records sort before CLOSED records.
- Closing a tracking record requires confirmation and immediately reflects the frozen CLOSED state.
- CLOSED record deletion requires confirmation; Scanner records warn that evidence used for Scanner performance analysis will be removed.
- Waiting records explicitly explain that performance starts from the next trading day.
- Bulk refresh reports when no new confirmed trading day exists.
- Empty states explain how to start tracking instead of only saying that no rows match.

## Not changed

- Production Scanner algorithm / ranking / strategy / entry / stop / targets
- Scanner recommendation count policy
- Tracking DB schema and performance formulas
- Historical Validation / legacy Simulation

## Apply

From the StockScope project root:

```powershell
python .\apply_track1102_tracking_lifecycle.py
```
