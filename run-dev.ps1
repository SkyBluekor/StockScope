$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Missing .venv. Run .\setup.ps1 first."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm 명령을 찾을 수 없습니다. Node.js LTS 설치 후 새 PowerShell에서 다시 실행하세요."
}

$python = Join-Path $root ".venv\Scripts\python.exe"

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\backend'; & '$python' -m uvicorn app.main:app --reload"
)

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\frontend'; npm run dev"
)

Write-Host "StockScope dev servers started." -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend : http://127.0.0.1:8000"
Write-Host "Swagger : http://127.0.0.1:8000/docs"
