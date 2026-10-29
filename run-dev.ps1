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

# A previous uvicorn --reload/frontend process can continue to serve another
# SQLite store. Do not silently start duplicate windows while its port is held.
# In particular, a printed 'started' message must never imply the new backend
# is the one responding on localhost:8000.
if ($env:STOCKSCOPE_SIM_DB) {
    if (-not (Test-Path -LiteralPath $env:STOCKSCOPE_SIM_DB -PathType Leaf)) {
        throw "[StockScope] STOCKSCOPE_SIM_DB does not exist: $env:STOCKSCOPE_SIM_DB"
    }
    Write-Host "[StockScope] Backend simulation DB: $env:STOCKSCOPE_SIM_DB"
} else {
    Write-Host "[StockScope] Backend simulation DB: project default"
}

foreach ($port in @(8000, 5173)) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        $ownerIds = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        throw "[StockScope] Port $port is already in use (PID: $ownerIds). Stop the existing backend/frontend windows with Ctrl+C before running .\run-dev.ps1. No new servers were started."
    }
}

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

Write-Host "StockScope dev server launches requested (check each console for readiness)." -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend : http://127.0.0.1:8000"
Write-Host "Swagger : http://127.0.0.1:8000/docs"
