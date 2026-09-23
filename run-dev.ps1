$ErrorActionPreference = "Stop"

try { chcp.com 65001 | Out-Null } catch {}
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "[StockScope] Missing .venv. Run .\setup.ps1 first."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "[StockScope] Command 'npm' was not found. Install Node.js LTS and restart PowerShell."
}

$python = Join-Path $root ".venv\Scripts\python.exe"

$backendCommand = "chcp.com 65001 > `$null; `$env:PYTHONUTF8='1'; `$env:PYTHONIOENCODING='utf-8'; Set-Location '$root\backend'; & '$python' -m uvicorn app.main:app --reload"
$frontendCommand = "chcp.com 65001 > `$null; Set-Location '$root\frontend'; npm run dev"

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    $backendCommand
)

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    $frontendCommand
)

Write-Host "StockScope dev servers started." -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend : http://127.0.0.1:8000"
Write-Host "Swagger : http://127.0.0.1:8000/docs"
