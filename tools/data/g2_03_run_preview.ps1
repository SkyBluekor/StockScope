param(
    [Parameter(Mandatory = $true)][string]$OperationalRepo,
    [string]$PreviewDir = (Join-Path $env:TEMP "StockScope_G2_03_ReadOnlyPreview")
)
$ErrorActionPreference = "Stop"
try { chcp.com 65001 | Out-Null } catch {}
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$work = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$repo = (Resolve-Path $OperationalRepo).Path
$py = Join-Path $repo ".venv\Scripts\python.exe"
$frontend = Join-Path $work "frontend"
$preview = [System.IO.Path]::GetFullPath($PreviewDir)
if (-not (Test-Path $py)) { throw "Operational Python venv missing: $py" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm is required." }
foreach ($port in @(8000, 5173)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is in use. Stop the existing StockScope servers."
    }
}
if (-not (Test-Path (Join-Path $frontend "package-lock.json"))) { throw "package-lock.json missing" }

$srcSim = Join-Path $repo "backend\runtime\simulation\simulation.db"
$srcMarket = Join-Path $repo "backend\runtime\market_history\market_history.db"
& $py (Join-Path $work "tools\data\g2_03_prepare_preview_stores.py") `
  --operational-simulation $srcSim `
  --operational-market $srcMarket `
  --preview-dir $preview
if ($LASTEXITCODE -ne 0) { throw "SQLite snapshot backup failed" }

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Push-Location $frontend
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    } finally { Pop-Location }
}
function QuotePs([string]$value) { return "'" + $value.Replace("'", "''") + "'" }

$backendDir = QuotePs (Join-Path $work "backend")
$frontendDir = QuotePs $frontend
$python = QuotePs $py
$sim = QuotePs (Join-Path $preview "simulation.db")
$market = QuotePs (Join-Path $preview "market_history.db")
$holdings = QuotePs (Join-Path $preview "holdings.db")

# Main app startup can update pending statuses; use COPIES for every operational store.
$backendCommand = (
    "`$env:PYTHONUTF8='1'; " +
    "`$env:PYTHONIOENCODING='utf-8'; " +
    "`$env:STOCKSCOPE_SIM_DB=$sim; " +
    "`$env:STOCKSCOPE_MARKET_STORE_DB=$market; " +
    "`$env:STOCKSCOPE_HOLDINGS_DB=$holdings; " +
    "Set-Location $backendDir; " +
    "& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)
$frontendCommand = "Set-Location $frontendDir; npm run dev -- --host 127.0.0.1"
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $backendCommand)
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $frontendCommand)
Write-Host "G2-03 isolated preview servers started" -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:5173"
Write-Host "Backend: http://127.0.0.1:8000"
Write-Host "Operational Simulation/Market DB paths are not connected." -ForegroundColor Yellow
Write-Host "Captures saved after this snapshot require a new preview backup."
