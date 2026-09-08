@echo off
setlocal
cd /d "%~dp0"

echo [StockScope] Applying v0.3.3 missing styles fix...

if not exist "frontend\src" (
  echo [ERROR] frontend\src folder not found.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [WARN] .venv was not found. This patch only verifies frontend build.
)

pushd frontend
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
echo [DONE] styles.css restored and frontend build passed.
echo Next: run .\run-dev.ps1
pause
endlocal
