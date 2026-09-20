# MERGE NOTES v0.21.4-B.2.3.4c.4g

## 적용
repo root에서 overlay를 덮어쓴 뒤 반드시 Production strategy patcher를 1회 실행한다.

```powershell
python backend\tools\apply_c4g_breakout_rs_production_fix.py
```

성공 출력은 다음 형태다.

```text
c.4g Breakout RS Production fix: patched
market weights=[10.0], sector weights=[8.0]
historical Sector RS activation gate was not changed
```

이미 적용된 상태에서 재실행하면 `already-applied`로 안전하게 종료한다.

## Focused test
```powershell
pytest backend\tests\test_breakout_rs_production_v0214b234c4g.py `
       backend\tests\test_sector_rs_counterfactual_v0214b234c4f4.py `
       backend\tests\test_sector_rs_audit_coverage_v0214b234c4f3.py -q
```

그 다음 기존 MA120/Sector/determinism regression을 실행한다.

## 10D acceptance
```powershell
python backend\tools\run_scanner_strategy_integrity_audit.py `
  --mode full `
  --market-scope ALL `
  --evaluation-dates-file backend\tools\audit_inputs\c4c_10days.txt `
  --min-required-dates 10 `
  --sector-rs-audit-live
```

## 80D acceptance
```powershell
python backend\tools\run_scanner_strategy_integrity_audit.py `
  --mode full `
  --market-scope ALL `
  --sample-size 80 `
  --min-date-gap 3 `
  --min-required-dates 80 `
  --sector-rs-audit-live
```

## 주의
`STATIC_CURRENT` OpenDART industry metadata를 historical point-in-time metadata처럼 Production에 넣지 않는다.
