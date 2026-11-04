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
if ($work -eq $repo) { throw "Preview must use a separate detached worktree." }
$py = Join-Path $repo ".venv\Scripts\python.exe"
$frontend = Join-Path $work "frontend"
$preview = [System.IO.Path]::GetFullPath($PreviewDir)

if (-not (Test-Path -LiteralPath $py)) { throw "Operational Python venv missing." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm is required." }
foreach ($port in @(8000, 5173)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use; stop the prior StockScope server."
    }
}
if (-not (Test-Path (Join-Path $frontend "package-lock.json"))) {
    throw "Frontend lockfile missing."
}

$srcSim = Join-Path $repo "backend\runtime\simulation\simulation.db"
$srcMarket = Join-Path $repo "backend\runtime\market_history\market_history.db"
$srcKrxDir = Join-Path $repo "backend\runtime\krx"
$dstKrxDir = Join-Path $work "backend\runtime\krx"
$srcBudget = Join-Path $srcKrxDir "budget.sqlite3"
$dstBudget = Join-Path $dstKrxDir "budget.sqlite3"

$backupArgs = @(
    "--operational-simulation", $srcSim,
    "--operational-market", $srcMarket,
    "--preview-dir", $preview
)
if (Test-Path -LiteralPath $srcBudget) {
    $backupArgs += @("--operational-krx-budget", $srcBudget, "--preview-krx-budget", $dstBudget)
}
& $py (Join-Path $work "tools\data\g2_03_prepare_preview_stores.py") @backupArgs
if ($LASTEXITCODE -ne 0) { throw "SQLite snapshot backup failed." }

# Copies of public KRX cached responses only; never overwrite live caches.
if (Test-Path -LiteralPath $srcKrxDir) {
    New-Item -ItemType Directory -Path $dstKrxDir -Force | Out-Null
    & robocopy.exe $srcKrxDir $dstKrxDir *.json.gz /S /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "KRX public cache copy failed." }
}

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Push-Location $frontend
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    } finally {
        Pop-Location
    }
}

# The detached worktree does not contain the user's original .env.
# Inherit only the KRX key; never copy brokerage or account secrets.
$originalKrxKey = [Environment]::GetEnvironmentVariable("KRX_API_KEY", "Process")
$previewKrxKey = $originalKrxKey
$envFile = Join-Path $repo ".env"
if ([string]::IsNullOrWhiteSpace($previewKrxKey) -and (Test-Path -LiteralPath $envFile)) {
    $keyLine = Get-Content -LiteralPath $envFile |
        Where-Object { $_ -match '^\s*(?:export\s+)?KRX_API_KEY\s*=' } |
        Select-Object -First 1
    if ($keyLine) {
        $parts = $keyLine -split '=', 2
        if ($parts.Count -eq 2) {
            $previewKrxKey = $parts[1].Trim()
            if ($previewKrxKey.Length -ge 2 -and (
                ($previewKrxKey.StartsWith("'") -and $previewKrxKey.EndsWith("'")) -or
                ($previewKrxKey.StartsWith('"') -and $previewKrxKey.EndsWith('"'))
            )) {
                $previewKrxKey = $previewKrxKey.Substring(1, $previewKrxKey.Length - 2)
            }
        }
    }
}
if ([string]::IsNullOrWhiteSpace($previewKrxKey)) {
    Write-Warning "KRX_API_KEY not found. New Scanner network requests might need credentials."
}

function QuotePs([string]$value) {
    return "'" + $value.Replace("'", "''") + "'"
}
$backendDir = QuotePs (Join-Path $work "backend")
$frontendDir = QuotePs $frontend
$python = QuotePs $py
$sim = QuotePs (Join-Path $preview "simulation.db")
$market = QuotePs (Join-Path $preview "market_history.db")
$holdings = QuotePs (Join-Path $preview "holdings.db")

$backendCommand = (
    '$env:PYTHONUTF8="1"; ' +
    '$env:PYTHONIOENCODING="utf-8"; ' +
    '$env:STOCKSCOPE_SIM_DB=' + $sim + '; ' +
    '$env:STOCKSCOPE_MARKET_STORE_DB=' + $market + '; ' +
    '$env:STOCKSCOPE_HOLDINGS_DB=' + $holdings + '; ' +
    'Set-Location ' + $backendDir + '; ' +
    '& ' + $python + ' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000'
)
$frontendCommand = 'Set-Location ' + $frontendDir + '; npm run dev -- --host 127.0.0.1'

try {
    if (-not [string]::IsNullOrWhiteSpace($previewKrxKey)) {
        $env:KRX_API_KEY = $previewKrxKey
    }
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", $backendCommand)
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", $frontendCommand)
} finally {
    [Environment]::SetEnvironmentVariable("KRX_API_KEY", $originalKrxKey, "Process")
}
Write-Host "StockScope isolated preview started." -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:5173"
Write-Host "Backend: http://127.0.0.1:8000"
Write-Host "Only preview copies of Simulation and Market DB are used." -ForegroundColor Yellow
Write-Host "New Scanner captures in preview do not write back to operational DB."
