# P0-05/G1 operator-controlled missing KRX market day recovery.
# No API calls or operational writes before explicit entitlement and write consent.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OperationalRepo
)
$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path -LiteralPath $OperationalRepo).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
$market = Join-Path $repo 'backend\runtime\market_history\market_history.db'
$repair = Join-Path $PSScriptRoot 'p0_05_market_gap_recovery.py'
$audit = Join-Path $PSScriptRoot 'p0_02_operational_store_audit.py'
$commonArgs = @(
    '--market-db', $market,
    '--date', '2026-10-22',
    '--date', '2026-10-23',
    '--date', '2026-10-26',
    '--date', '2026-10-27'
)
$requests = 16

foreach ($file in @($python, $market, $repair, $audit)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw 'Missing required local file; no recovery was started.'
    }
}
Write-Host 'P0-05/G1: read-only local preflight, then 4 days x 2 markets x 2 endpoints.'

$preflightArgs = @('--check-local-setup', '--operational-repo', $repo) + $commonArgs + @('--max-requests', [string]$requests)
$json = & $python $repair @preflightArgs
if ($LASTEXITCODE -ne 0) { throw 'Local configuration preflight HOLD; no recovery.' }
$local = ($json | Out-String | ConvertFrom-Json)
if ($local.status -ne 'LOCAL_KRX_CONFIGURATION_PRESENT_APPROVAL_REQUIRED' -or
    $local.krx_credential_configured -ne $true -or
    $local.local_budget_allows_cap -ne $true -or
    $local.provider_request_floor -ne 16 -or
    $local.missing_market_days -ne 8) {
    throw 'Local KRX configuration, budget or missing-day evidence mismatch.'
}

Write-Host 'Verify FOUR KRX portal service applications are explicitly APPROVED:'
Write-Host 'KOSPI stock daily; KOSDAQ stock daily; KOSPI index series daily; KOSDAQ index series daily.'
Write-Host 'The local presence of an API key does NOT establish service permissions.'
$rights = Read-Host 'Only if all four are approved and your use is authorized, type KRX4_APPROVED'
if ($rights -cne 'KRX4_APPROVED') {
    Write-Host 'HOLD_SERVICE_ENTITLEMENT_UNCONFIRMED (no API calls or writes)'
    throw 'Operator aborted or recovery failed; inspect the previous status.'
}
Write-Host 'Action: max 16 KRX attempts (incl retries), then ALL-or-NOTHING insertion of 8 missing market-days.'
Write-Host 'Existing days cannot be overwritten; Scanner, Prospective Capture, orders and scheduler are not run.'
$approval = Read-Host 'Approve these external requests AND operational Market DB writes: type RESTORE_16_WRITE'
if ($approval -cne 'RESTORE_16_WRITE') {
    Write-Host 'HOLD_EXECUTION_NOT_APPROVED (no API calls or writes)'
    throw 'Operator aborted or recovery failed; inspect the previous status.'
}

# SQLite online backup is WAL-safe; create outside Git repository.
$backupDir = Join-Path $env:LOCALAPPDATA 'StockScope\market_backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss_ffff'
$backup = Join-Path $backupDir ("market_history_before_G1_" + $timestamp + '.db')
if (Test-Path -LiteralPath $backup) { throw 'Backup already exists.' }
$backupScript = @'
import sqlite3, sys
from pathlib import Path
src, dst = map(Path, sys.argv[1:3])
if not src.is_file() or dst.exists():
    raise SystemExit("Backup source missing or target exists")
with sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True, timeout=20) as original:
    with sqlite3.connect(dst, timeout=20) as saved:
        original.backup(saved)
with sqlite3.connect(dst.resolve().as_uri() + "?mode=ro", uri=True) as checked:
    if checked.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise SystemExit("Backup integrity check failed")
'@
& $python -c $backupScript $market $backup
if ($LASTEXITCODE -ne 0) {
    throw 'SQLite backup failed. No KRX request has been sent.'
}
Write-Host "Verified pre-repair backup: $backup"

$runArgs = @('--run-approved', '--operational-repo', $repo) + $commonArgs + @(
    '--max-requests', [string]$requests,
    '--approve-krx-requests', '--approve-market-write', '--confirm-source-rights'
)
& $python $repair @runArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host 'HOLD_REPAIR_FAILED. No Scanner/Capture was executed.'
    Write-Host "Pre-repair backup retained: $backup"
    throw 'Operator aborted or recovery failed; inspect the previous status.'
}

Write-Host 'Read-only audit of actual persisted rows:'
& $python $audit '--market-db' $market '--as-of' '2026-10-27' '--market-scope' 'ALL' '--lookback-calendar-days' '14'
if ($LASTEXITCODE -ne 0) {
    Write-Host 'HOLD_POST_REPAIR_AUDIT_FAILED. Do not launch Scanner/G1.'
    Write-Host "Pre-repair backup retained: $backup"
    throw 'Operator aborted or recovery failed; inspect the previous status.'
}
Write-Host 'Audit completed; check stock AND index latest date in KOSPI and KOSDAQ.'
Write-Host 'Prospective Capture, scheduler and real trading were NOT started.'
Write-Host "Pre-repair backup retained: $backup"
