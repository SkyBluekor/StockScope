# P0-05/G1 one-time, human-initiated first Prospective Capture.
# No scheduled task. Do not use this script to backfill a missed morning.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OperationalRepo,
    [ValidateSet('ALL','KOSPI','KOSDAQ')]
    [string]$Scope = 'ALL',
    [ValidateRange(16,1024)]
    [int]$MaxKrxRequests = 128
)
$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path -LiteralPath $OperationalRepo).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
$script = Join-Path $PSScriptRoot 'p0_05_g1_capture_once.py'
$simulation = Join-Path $repo 'backend\runtime\simulation\simulation.db'
$market = Join-Path $repo 'backend\runtime\market_history\market_history.db'
foreach ($file in @($python, $script, $simulation, $market)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw 'Missing operational file. No G1 process started.'
    }
}

$preflightArgs = @(
    '--operational-repo', $repo, '--scope', $Scope,
    '--candidate-limit', '5', '--max-krx-requests', [string]$MaxKrxRequests
)
$raw = & $python $script @preflightArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host ($raw | Out-String)
    throw 'HOLD_G1_PREFLIGHT: no KRX calls or Scanner started.'
}
$report = ($raw | Out-String | ConvertFrom-Json)
if ($report.status -cne 'LOCAL_G1_ELIGIBLE_APPROVAL_REQUIRED') {
    throw 'HOLD_G1_PREFLIGHT: eligibility not verified.'
}

Write-Host 'Opt-in G1: a new Scanner run can call KRX, update Market Store, and persist one immutable Prospective Capture.'
Write-Host ('Scope: ' + $Scope + '. Approved maximum KRX HTTP attempts incl retries: ' + $MaxKrxRequests)
Write-Host 'Confirm KRX portal service permissions covering the full Scanner workflow (daily stock/index and any supplementary endpoint used).'
Write-Host 'Your previous 4-day repair permission does not by itself authorize a new Scanner capture.'
$rights = Read-Host 'Only if this use is authorized, type G1_KRX_SERVICES_APPROVED'
if ($rights -cne 'G1_KRX_SERVICES_APPROVED') {
    throw 'HOLD_G1_KRX_SERVICE_RIGHTS: no network requests or DB writes.'
}
$approve = Read-Host ('Approve new KRX requests (cap ' + $MaxKrxRequests + ') and operational Simulation/Market writes: type G1_CAPTURE_APPROVED')
if ($approve -cne 'G1_CAPTURE_APPROVED') {
    throw 'HOLD_G1_CAPTURE_NOT_APPROVED: no network requests or DB writes.'
}

# WAL-consistent online backup of both operational Simulation and Market
# DBs. Scanner can update either; never do a raw copy of an open WAL database.
$backupDir = Join-Path $env:LOCALAPPDATA 'StockScope\g1_capture_backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss_ffff'
$backup = Join-Path $backupDir ("simulation_before_G1_" + $timestamp + '.db')
$marketBackup = Join-Path $backupDir ("market_before_G1_" + $timestamp + '.db')
$backupScript = @'
import sqlite3, sys
from pathlib import Path
src, dst = map(Path, sys.argv[1:3])
if not src.is_file() or dst.exists():
    raise SystemExit("Simulation backup source missing or destination exists")
with sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True, timeout=20) as original:
    with sqlite3.connect(dst, timeout=20) as saved:
        original.backup(saved)
with sqlite3.connect(dst.resolve().as_uri() + "?mode=ro", uri=True) as checked:
    if checked.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise SystemExit("Simulation backup integrity failure")
'@
& $python -c $backupScript $simulation $backup
if ($LASTEXITCODE -ne 0) {
    throw 'HOLD_G1_BACKUP_FAILED: Scanner not started.'
}
& $python -c $backupScript $market $marketBackup
if ($LASTEXITCODE -ne 0) {
    throw 'HOLD_G1_MARKET_BACKUP_FAILED: Scanner not started.'
}
Write-Host "Verified pre-capture Simulation backup: $backup"
Write-Host "Verified pre-capture Market backup: $marketBackup"

$approvedArgs = $preflightArgs + @(
    '--run-approved', '--approve-krx-requests',
    '--approve-simulation-write', '--confirm-krx-services'
)
& $python $script @approvedArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "Simulation backup retained: $backup; Market backup retained: $marketBackup"
    throw 'HOLD_G1_CAPTURE_FAILED: inspect the JSON status; never auto-retry.'
}
Write-Host 'Inspect returned s17 persisted_capture_verified, snapshot hashes, dates and capture status.'
Write-Host 'No recurring schedule or strategy approval was registered.'
Write-Host "Simulation backup retained: $backup; Market backup retained: $marketBackup"
