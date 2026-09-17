# v0.21.4-B.2.3.4a — Windows timezone hotfix

## Problem
`reproducibility_audit.py` created `ZoneInfo("Asia/Seoul")` at import time. On Windows Python installations without the `tzdata` package, backend startup failed with `ZoneInfoNotFoundError`, so Vite received `ECONNREFUSED 127.0.0.1:8000`.

## Fix
Replace IANA ZoneInfo lookup with a fixed UTC+09:00 timezone using the Python standard library only. Korea has no DST, so this preserves the intended KST timestamps without adding a package dependency.

## Scope
Only `backend/app/backtest/reproducibility_audit.py` changes. Scanner/ranking/Target/Risk/Market Store logic is unchanged.
