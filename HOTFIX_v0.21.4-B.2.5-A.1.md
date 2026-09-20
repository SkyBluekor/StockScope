# v0.21.4-B.2.5-A.1 — Scanner base-version regression hotfix

## Problem
B.2.5-A overlay accidentally packaged `backend/app/backtest/scanner.py` from the B.2.4 / Scanner VERSION 0.21.3.5 base.
Applying it over the latest working tree could regress Scanner decision/cache version from 0.21.3.6 to 0.21.3.5.

## Fix
This hotfix restores the scanner implementation from the Target1 Production Policy Correction base:
- `MultiStrategyStockScanner.VERSION = "0.21.3.6"`
- `HISTORICAL_EVIDENCE_POLICY_VERSION = "v2"`

Then reapplies only the B.2.5-A diagnostic strategy-trace additions.

## Production policy
No Strategy/Ranking/Risk/Entry/Stop/Target formula is intentionally changed by this hotfix.
