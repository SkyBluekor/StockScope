$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Require-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "[StockScope] '$Name' 명령을 찾을 수 없습니다. $InstallHint"
    }
}

function Assert-LastExitCode {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "[StockScope] $Step 실패 (exit code: $LASTEXITCODE)"
    }
}

Write-Host "[StockScope] Checking prerequisites..." -ForegroundColor Cyan
Require-Command "python" "Python 3.11 이상을 설치하고 새 PowerShell을 여세요."
Require-Command "node" "Node.js LTS를 설치하세요: winget install OpenJS.NodeJS.LTS"
Require-Command "npm" "Node.js LTS를 설치한 뒤 PowerShell을 완전히 닫았다가 다시 여세요."

$pythonVersion = (& python --version 2>&1)
Assert-LastExitCode "Python version check"
$nodeVersion = (& node --version 2>&1)
Assert-LastExitCode "Node.js version check"
$npmVersion = (& npm --version 2>&1)
Assert-LastExitCode "npm version check"

Write-Host "  Python: $pythonVersion"
Write-Host "  Node  : $nodeVersion"
Write-Host "  npm   : $npmVersion"

Write-Host "[StockScope] Setting up backend..." -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & python -m venv .venv
    Assert-LastExitCode "virtual environment creation"
}

$python = Join-Path $root ".venv\Scripts\python.exe"

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
