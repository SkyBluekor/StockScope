[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [Parameter(DontShow = $true)]
    [switch]$AfterSelfUpdate
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

        $BeforeHead = (& git rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $BeforeHead) {
            Fail "Unable to resolve pre-update Git HEAD."
        }

        & git fetch origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git fetch origin main failed. Runtime migration was not started."
        }

        & git pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git pull --ff-only origin main failed. Local main may have diverged."
        }

        $AfterHead = (& git rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $AfterHead) {
            Fail "Unable to resolve post-update Git HEAD."
        }

        Write-Host "Git update              PASS  origin/main"

        if (-not $AfterSelfUpdate -and $BeforeHead -ne $AfterHead) {
            $SelfChanges = @(
                & git diff --name-only "$BeforeHead..$AfterHead" -- "sync_local.ps1"
            )
            if ($LASTEXITCODE -ne 0) {
                Fail "Unable to inspect whether sync_local.ps1 changed during update."
            }

            if ($SelfChanges.Count -gt 0) {
                Write-Host "Local Sync script       UPDATED - restarting once"

                $Pwsh = Join-Path $PSHOME "pwsh.exe"
                $WindowsPowerShell = Join-Path $PSHOME "powershell.exe"
                if (Test-Path $Pwsh -PathType Leaf) {
                    $PowerShellExe = $Pwsh
                } elseif (Test-Path $WindowsPowerShell -PathType Leaf) {
                    $PowerShellExe = $WindowsPowerShell
                } else {
                    Fail "Unable to locate the current PowerShell executable for self-restart."
                }

                & $PowerShellExe -NoProfile -File $PSCommandPath -AfterSelfUpdate
                exit $LASTEXITCODE
            }
        }
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
    $MacroArguments = @((Join-Path $Root "tools\dev\sync_macro_artifacts.py"))
    if ($CheckOnly) {
        $MacroArguments += "--check-only"
    }

    & $Python @MacroArguments
    $MacroExit = $LASTEXITCODE
    if ($MacroExit -ne 0) {
        Fail "Macro artifact synchronization failed with exit code $MacroExit."
    }
    Write-Host "Macro artifact chain    PASS  through Reference Adequacy Evidence"

    Write-Host ""
    Write-Host "Git/Secrets"
    Write-Host "Secrets                 UNCHANGED"
    Write-Host "Git destructive ops     NONE"
    exit 0
}
catch {
    Fail $_.Exception.Message
}
