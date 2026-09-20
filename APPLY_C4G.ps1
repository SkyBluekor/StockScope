$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $RepoRoot
try {
    python backend\tools\apply_c4g_breakout_rs_production_fix.py
    Write-Host ""
    Write-Host "c.4g source patch complete. Run focused tests next:"
    Write-Host "pytest backend\tests\test_breakout_rs_production_v0214b234c4g.py backend\tests\test_sector_rs_counterfactual_v0214b234c4f4.py backend\tests\test_sector_rs_audit_coverage_v0214b234c4f3.py -q"
}
finally {
    Pop-Location
}
