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
if (-not (Test-Path $py)) { throw "운영 Python 가상환경을 찾을 수 없습니다: $py" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm이 필요합니다." }
foreach ($port in @(8000, 5173)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "포트 $port 사용 중입니다. 기존 StockScope 서버를 종료하세요."
    }
}
if (-not (Test-Path (Join-Path $frontend "package-lock.json"))) { throw "package-lock.json 없음" }

$srcSim = Join-Path $repo "backend\runtime\simulation\simulation.db"
$srcMarket = Join-Path $repo "backend\runtime\market_history\market_history.db"
& $py (Join-Path $work "tools\data\g2_03_prepare_preview_stores.py") `
  --operational-simulation $srcSim `
  --operational-market $srcMarket `
  --preview-dir $preview
if ($LASTEXITCODE -ne 0) { throw "스냅샷 복제 실패" }

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Push-Location $frontend
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci 실패" }
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
Write-Host "G2-03 격리 미리보기 서버 시작" -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:5173"
Write-Host "Backend: http://127.0.0.1:8000"
Write-Host "운영 Simulation/Market DB와 직접 연결하지 않습니다." -ForegroundColor Yellow
Write-Host "이후 수집 기록은 다시 복제하기 전까지 표시되지 않습니다."
