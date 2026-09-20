# Merge Notes — v0.21.4-B.2.4

Apply this overlay on top of the current repository after c.4g.

## Replaced files
- `backend/app/backtest/scanner.py` — based on c.4g Scanner `0.21.3.5`
- `backend/app/api/backtest.py` — adds `known_data_date` to Scanner job and unified freshness+analysis relay
- `frontend/src/components/ScannerPanel.tsx` — based on deterministic Scanner UI path

## New files
- `frontend/src/components/scannerProgress.ts`
- `frontend/src/components/scannerProgress.css`
- `backend/tests/test_scanner_progress_contract_v0214b24.py`

## Important
Do not overwrite these files afterward with an older B.2.2/B.2.3 overlay. In particular `scanner.py` already contains the c.4g Production Breakout RS correction context and Scanner version `0.21.3.5`.

## Suggested verification
```powershell
pytest backend\tests\test_scanner_progress_contract_v0214b24.py -q
npm --prefix frontend run build
```

Then run Scanner twice on the same market scope:
1. first run: inspect latest EOD/KRX stage progression
2. second run: confirm `저장 데이터 재사용` and no fake 0% pause

Candidate codes/rank/strategy/risk/entry-stop-target should remain unchanged for the same input fingerprint.
