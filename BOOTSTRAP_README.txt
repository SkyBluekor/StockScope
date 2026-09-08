StockScope bootstrap overlay v0.1

Purpose
- Executable FastAPI + React/Vite starter
- Frontend-to-backend health check
- Hard read-only policy: no real brokerage order routes
- BYOK placeholders only; no real credentials included

Fast path
1. Extract every file in this ZIP directly into D:\Projects\StockScope and overwrite the current empty scaffold files.
2. Open PowerShell at D:\Projects\StockScope.
3. Run:
      .\setup.ps1
4. After setup succeeds, run:
      .\run-dev.ps1
5. Open:
      http://127.0.0.1:5173

Expected validation
- setup.ps1: backend pytest passes.
- setup.ps1: frontend build completes.
- UI: API 정상.
- http://127.0.0.1:8000/ returns real_trading=false.
- http://127.0.0.1:8000/docs contains no real order endpoint.

Important
- Existing .gitignore is intentionally NOT included or modified.
- No .env file or real secret is included.
- Actual KIS buy/sell/order APIs are intentionally absent.
