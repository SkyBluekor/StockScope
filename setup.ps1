$ErrorActionPreference = "Stop"

Write-Host "[StockScope] Setting up backend..." -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$python = Join-Path (Resolve-Path ".venv") "Scripts\python.exe"
$pip = Join-Path (Resolve-Path ".venv") "Scripts\pip.exe"

& $python -m pip install --upgrade pip
& $pip install -e ".\backend[dev]"

Push-Location backend
try {
    & $python -m pytest
}
finally {
    Pop-Location
}

Write-Host "[StockScope] Setting up frontend..." -ForegroundColor Cyan
Push-Location frontend
try {
    npm install
    npm run build
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "[StockScope] Setup complete." -ForegroundColor Green
Write-Host "Run .\run-dev.ps1 and open http://127.0.0.1:5173"
