@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync_local.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo StockScope Local Sync failed. See the message above.
) else (
  echo StockScope Local Sync finished successfully.
)
echo.
pause
exit /b %EXITCODE%
