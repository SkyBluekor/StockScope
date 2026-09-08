@echo off
setlocal
cd /d "%~dp0"

echo [StockScope v0.3] KIS 필수 경로 제거 및 KRX + OpenDART 구성 적용

if exist "backend\app\api\kis.py" del /q "backend\app\api\kis.py"
if exist "backend\tests\test_kis_read_only.py" del /q "backend\tests\test_kis_read_only.py"

echo.
set /p KRX_KEY=KRX API 인증키를 입력하세요: 
set /p DART_KEY=OpenDART API 인증키를 입력하세요: 

> ".env" echo KRX_API_KEY=%KRX_KEY%
>> ".env" echo DART_API_KEY=%DART_KEY%
>> ".env" echo ENVIRONMENT=development

set KRX_KEY=
set DART_KEY=

echo.
echo .env 저장 완료 ^(.gitignore 대상^)

echo.
echo Backend 테스트 실행 중...
pushd backend
"..\.venv\Scripts\python.exe" -m pytest
if errorlevel 1 (
  popd
  echo.
  echo [ERROR] 테스트 실패. 위 로그를 확인해주세요.
  exit /b 1
)
popd

echo.
echo Frontend build 확인 중...
pushd frontend
call npm run build
if errorlevel 1 (
  popd
  echo.
  echo [ERROR] Frontend build 실패. 위 로그를 확인해주세요.
  exit /b 1
)
popd

echo.
echo [DONE] v0.3 적용 완료.
echo run-dev.ps1을 다시 실행하세요.
endlocal
