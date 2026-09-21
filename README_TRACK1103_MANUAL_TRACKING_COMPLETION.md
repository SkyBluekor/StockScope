# TRACK.1.10.3 — Manual Tracking Completion

This overlay finishes the user-facing manual stock-tracking flow without changing Scanner production logic, Tracking DB schema, performance formulas, or Historical Validation.

## Scope

- Keep stock-name/code search available without running Scanner first.
- Show the confirmed Market Store reference date and close before manual tracking starts.
- Keep the selected search context visible after creation so the result immediately becomes `추적 중` without a reload.
- Prevent same-confirmed-day reopen in the UI when a manual episode was already closed that day; the backend policy remains the source of truth.
- Keep SCANNER and MANUAL episodes independent.
- Make row actions explicit: `최신 반영`, `추적 종료`, `기록 삭제`.
- Show current price separately from current return in expanded details.
- Report `새로운 확정 거래일이 없습니다.` when an individual refresh produces no newer performance state.

## Not changed

- Scanner ranking/strategy/risk/entry/stop/targets
- Scanner recommendation count
- Tracking database schema
- D+1 / 5D / 10D / 20D performance formulas
- Historical Validation / Legacy Simulation

## Apply

Run from the StockScope project root:

```powershell
python .\apply_track1103_manual_tracking.py
```

The script backs up changed files, runs focused regression tests and the frontend production build, and rolls back this overlay if a test/build fails.
