$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$ErrorActionPreference = 'Stop'

python backend\tools\apply_b25c_ranking_tiebreak.py
python -m pytest -q backend\tests\test_candidate_priority_v0214b25c.py

Write-Host "" 
Write-Host "B.2.5-C applied and focused tests passed." -ForegroundColor Green
Write-Host "Run Scanner '다시 분석', then:" 
Write-Host "python backend\tools\run_scanner_decision_quality_audit.py --top 5"
