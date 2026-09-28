[CmdletBinding()]
param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSCommandPath
Set-Location $Root

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "=============================================================================="
    Write-Host "STOCKSCOPE LOCAL SYNC BLOCKED"
    Write-Host "=============================================================================="
    Write-Host $Message
    Write-Host ""
    Write-Host "No automatic stash, reset, rebase, or force operation was performed."
    exit 1
}

try {
    $inside = (& git rev-parse --is-inside-work-tree 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $inside -ne "true") {
        Fail "This script must be run inside the StockScope Git repository."
    }

    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) {
        Fail "Unable to determine the current Git branch."
    }
    if ($branch -ne "main") {
        Fail "Current branch is '$branch'. Local Sync only runs from main."
    }

    $trackedChanges = @(& git status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0) {
        Fail "Unable to inspect the Git working tree."
    }
    if ($trackedChanges.Count -gt 0) {
        Write-Host "Tracked changes:"
        $trackedChanges | ForEach-Object { Write-Host "  $_" }
        Fail "Tracked working-tree changes must be committed or reverted first."
    }

    $untracked = @(& git ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        Fail "Unable to inspect untracked files."
    }

    Write-Host "=============================================================================="
    Write-Host "STOCKSCOPE LOCAL SYNC"
    Write-Host "=============================================================================="
    Write-Host ("Branch                  PASS  {0}" -f $branch)
    Write-Host ("Tracked working tree    PASS")
    if ($untracked.Count -gt 0) {
        Write-Host ("Untracked files         WARN  {0}" -f $untracked.Count)
    } else {
        Write-Host ("Untracked files         PASS  0")
    }

    if (-not $CheckOnly) {
        Write-Host ""
        Write-Host "Git update"
        & git fetch origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git fetch origin main failed. Runtime migration was not started."
        }

        & git pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git pull --ff-only origin main failed. Local main may have diverged."
        }
        Write-Host "Git update              PASS  origin/main"
    } else {
        Write-Host "Git update              SKIPPED (CheckOnly)"
    }

    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python -PathType Leaf)) {
        Fail "Python venv is missing: $Python"
    }
    Write-Host ("Python venv             PASS  {0}" -f $Python)
    Write-Host ""

    $Arguments = @((Join-Path $Root "tools\dev\sync_local.py"))
    if ($CheckOnly) {
        $Arguments += "--check-only"
    }

    & $Python @Arguments
    $PythonExit = $LASTEXITCODE
    if ($PythonExit -ne 0) {
        Fail "Runtime schema synchronization failed with exit code $PythonExit."
    }

    Write-Host ""
    Write-Host "Git/Secrets"
    Write-Host "Secrets                 UNCHANGED"
    Write-Host "Git destructive ops     NONE"
    exit 0
}
catch {
    Fail $_.Exception.Message
}
