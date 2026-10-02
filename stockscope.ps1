[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "sync")]
    [string]$Command = "status"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSCommandPath
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    Write-Error "Python venv is missing: $Python"
    exit 1
}

switch ($Command) {
    "status" {
        & $Python (Join-Path $Root "tools\dev\sync_local.py") --check-only
        exit $LASTEXITCODE
    }
    "sync" {
        & (Join-Path $Root "sync_local.ps1")
        exit $LASTEXITCODE
    }
}
