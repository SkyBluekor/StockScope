# Merge Notes — v0.21.4-B.2.5-A

## 기준

이 overlay는 다음 최근 산출물에서 확인된 코드 형태를 기준으로 작성했다.

- Scanner: `v0.21.4-B.2.4`
- deterministic candidate ranking / reproducibility: `v0.21.4-B.2.3.4b`
- Target1 metadata wiring: `v0.21.4-B.2.3.2d.2`

전체 프로젝트 snapshot을 재구성한 것이 아니다.

## 적용 전

```powershell
cd C:\TAEWOO\CapstonDesign\StockScope
git status
git diff --stat
```

미커밋 변경을 reset하지 않는다.

## 기존 파일 2개

- `backend/app/backtest/scanner.py`
- `backend/app/backtest/reproducibility_audit.py`

로컬 파일에 추가 변경이 있다면 overlay 파일로 무조건 덮어쓰지 말고 `PATCH_EXISTING_FILES_v0.21.4-B.2.5-A.diff`의 변경 부분만 병합한다.

## 새 파일

- `backend/app/backtest/scanner_quality/decision_quality_audit.py`
- `backend/tools/run_scanner_decision_quality_audit.py`
- `backend/tests/test_scanner_decision_quality_audit_v0214b25a.py`
- `backend/tests/test_repro_target1_strategy_trace_v0214b25a.py`

## focused tests

```powershell
python -m pytest -q `
  backend/tests/test_scanner_decision_quality_audit_v0214b25a.py `
  backend/tests/test_repro_target1_strategy_trace_v0214b25a.py
```

그 다음 Scanner `다시 분석` 후:

```powershell
python backend\tools\run_scanner_decision_quality_audit.py --top 5
```

## 회귀 안전선

이 overlay에서 다음 값이 바뀌면 의도하지 않은 회귀다.

- Strategy 계산값
- Ranking policy
- Risk 판단값
- Entry / Stop
- Target1 / Target2
- Historical Sector RS temporal gate
- MA120 no-lookahead
