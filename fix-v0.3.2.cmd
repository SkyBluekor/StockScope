@echo off
setlocal
cd /d "%~dp0"

echo [StockScope] TypeScript TS6310 fix verification
if not exist "frontend\package.json" (
  echo [ERROR] frontend\package.json not found.
  echo Run this file from the StockScope project root after copying it there.
  pause
  exit /b 1
)

pushd frontend
echo [1/1] Verifying frontend build...
call npm run build
if errorlevel 1 (
  echo.
  echo [ERROR] Frontend build failed. Keep this window open and send the error output.
  popd
  pause
  exit /b 1
)
popd

echo.
echo [DONE] TypeScript configuration fixed and frontend build passed.
echo Next: run .\run-dev.ps1
pause
