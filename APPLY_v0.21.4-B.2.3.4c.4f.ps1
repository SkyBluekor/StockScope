[CmdletBinding()]
param(
    [string]$RepoRoot = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
$overlay = Split-Path -Parent $PSCommandPath
$files = @(
    'backend/app/backtest/sector_rs_input.py',
    'backend/app/backtest/engine.py',
    'backend/tests/test_sector_rs_production_input_v0214b234c4f.py',
    'WORKSPEC_v0.21.4-B.2.3.4c.4f.md',
    'IMPLEMENTATION_v0.21.4-B.2.3.4c.4f.md',
    'MERGE_NOTES_v0.21.4-B.2.3.4c.4f.md'
)

foreach ($relative in $files) {
    $src = Join-Path $overlay $relative
    $dst = Join-Path $RepoRoot $relative
    $parent = Split-Path -Parent $dst
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host "Applied $relative"
}
