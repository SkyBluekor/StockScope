# MERGE NOTES v0.21.4-B.2.3.4c.4f.4

## 적용 순서
c.4f.3 적용본 위에 덮어쓴다.

## 주요 변경 파일
- `backend/app/backtest/scanner_quality/strategy_integrity_audit.py`
- `backend/tools/run_scanner_strategy_integrity_audit.py`
- `backend/tests/test_sector_rs_counterfactual_v0214b234c4f4.py`

## 검증
```powershell
pytest backend\tests\test_sector_rs_counterfactual_v0214b234c4f4.py -q
pytest backend\tests\test_sector_rs_audit_coverage_v0214b234c4f3.py -q
pytest backend\tests\test_sector_rs_prefetch_v0214b234c4f2.py -q
pytest backend\tests\test_sector_rs_production_input_v0214b234c4f.py -q
pytest backend\tests\test_ma120_production_input_v0214b234c4d.py -q
pytest backend\tests\test_scanner_determinism_v0214b234b.py -q
pytest backend\tests\test_scanner_strategy_integrity_audit.py -q
```

## 10D 실행
```powershell
python backend\tools\run_scanner_strategy_integrity_audit.py `
  --mode inspect `
  --evaluation-dates-file backend\tools\audit_inputs\c4c_10days.txt `
  --sector-rs-audit-live
```

현재 dorm PC의 Market Store에서 과거 날짜가 누락되어 2/10만 valid라면, 그 결과는 파이프라인 smoke evidence로만 취급하고 정책 결론은 내리지 않는다. historical snapshot이 충분한 환경에서 동일 10D/80D를 재실행한다.
