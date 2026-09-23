param(
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"

try { chcp.com 65001 | Out-Null } catch {}
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Require-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "[StockScope] Command '$Name' was not found. $InstallHint"
    }
}

function Assert-LastExitCode {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "[StockScope] $Step failed (exit code: $LASTEXITCODE)"
    }
}

function Remove-StockScopeVenv {
    if (Test-Path ".venv") {
        Write-Host "[StockScope] Removing existing .venv..." -ForegroundColor Yellow
        Remove-Item ".venv" -Recurse -Force
    }
}

Write-Host "[StockScope] Checking prerequisites..." -ForegroundColor Cyan
Require-Command "python" "Install Python 3.11+ and open a new PowerShell window."
Require-Command "node" "Install Node.js LTS: winget install OpenJS.NodeJS.LTS"
Require-Command "npm" "Install Node.js LTS, then fully restart PowerShell."

$pythonVersion = (& python --version 2>&1)
Assert-LastExitCode "Python version check"
$nodeVersion = (& node --version 2>&1)
Assert-LastExitCode "Node.js version check"
$npmVersion = (& npm --version 2>&1)
Assert-LastExitCode "npm version check"

$systemPythonMajorMinor = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1)
Assert-LastExitCode "Python major/minor version check"

Write-Host "  Python: $pythonVersion"
Write-Host "  Node  : $nodeVersion"
Write-Host "  npm   : $npmVersion"

$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if ($RecreateVenv) {
    Remove-StockScopeVenv
}
elseif (Test-Path $venvPython) {
    $venvPythonMajorMinor = (& $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1)
    if ($LASTEXITCODE -ne 0 -or $venvPythonMajorMinor -ne $systemPythonMajorMinor) {
        Write-Host "[StockScope] Existing .venv uses a different or broken Python runtime." -ForegroundColor Yellow
        Write-Host "  System Python: $systemPythonMajorMinor"
        Write-Host "  .venv Python : $venvPythonMajorMinor"
        Remove-StockScopeVenv
    }
}
elseif (Test-Path ".venv") {
    Write-Host "[StockScope] Existing .venv is incomplete. Recreating it..." -ForegroundColor Yellow
    Remove-StockScopeVenv
}

Write-Host "[StockScope] Setting up backend..." -ForegroundColor Cyan
if (-not (Test-Path $venvPython)) {
    Write-Host "[StockScope] Creating .venv with Python $systemPythonMajorMinor..." -ForegroundColor DarkCyan
    & python -m venv .venv
    Assert-LastExitCode "virtual environment creation"
}

$python = $venvPython

$venvVersion = (& $python --version 2>&1)
Assert-LastExitCode "virtual environment Python version check"
Write-Host "  .venv: $venvVersion"

& $python -m pip install --upgrade pip
Assert-LastExitCode "pip upgrade"
& $python -m pip install -e ".\backend[dev]"
Assert-LastExitCode "backend dependency install"

Write-Host "[StockScope] Backend versions..." -ForegroundColor DarkCyan
& $python -c "import fastapi, starlette, tzdata; print('  FastAPI:', fastapi.__version__); print('  Starlette:', starlette.__version__); print('  tzdata:', tzdata.__version__)"
Assert-LastExitCode "backend version check"

Push-Location backend
try {
    & $python -m pytest
    Assert-LastExitCode "backend tests"
}
finally {
    Pop-Location
}

Write-Host "[StockScope] Setting up frontend..." -ForegroundColor Cyan
Push-Location frontend
try {
    if (Test-Path "package-lock.json") {
        & npm ci
        Assert-LastExitCode "npm ci"
    }
    else {
        & npm install
        Assert-LastExitCode "npm install"
    }

    & npm run build
    Assert-LastExitCode "frontend build"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "[StockScope] Setup complete." -ForegroundColor Green
Write-Host "Run .\run-dev.ps1 and open http://127.0.0.1:5173"
Write-Host "Manual .venv activation is optional; run-dev.ps1 uses .venv directly."
