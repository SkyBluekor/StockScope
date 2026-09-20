# IMPLEMENTATION v0.21.4-B.2.3.2c
## Target1 Historical Realism Validation — Smoke First

### 추가 파일
- `backend/app/backtest/target1_realism_validation.py`
  - Production Scanner의 quick/current candidate 경로를 그대로 사용해 18개 후보를 만든다.
  - CURRENT / CAP_1_5R / FIXED_1_5R 세 Target만 counterfactual 비교한다.
  - Entry, invalidation, strategy, rank는 동일 신호에서 고정한다.
  - 5/10/20D first-touch, same-bar ambiguity, 거리/R/source bucket, extreme group을 집계한다.
  - B.2.3.2b의 `target1_audit` payload가 있으면 resistance/high20 동일가격도 구분한다.
- `backend/tools/run_target1_realism_audit.py`
  - 기본 20일 smoke run.
  - KRX network hard guard.
  - 기존 temporal date sampler 재사용.
  - JSON/CSV/Markdown 출력.
- `backend/tests/test_target1_realism_validation_v0214b232c.py`
  - 한미사이언스 수치형 fixture, 1.5R 계산, bucket, 동일봉 처리, source 분류, policy transition 검증.

### Production 변경
없음. Scanner `0.21.3.5`, RiskEngine Target1 공식, Technical resistance/high20, Ranking, Strategy, Entry/Stop/Target2/Exit 모두 그대로다.

### 구현 환경 검증
- Python compile: PASS
- focused unit tests: 6/6 PASS

### 실제 PC에서 필요한 검증
```powershell
pytest backend\tests\test_target1_realism_validation_v0214b232c.py -q
python backend\tools\run_target1_realism_audit.py --sample-size 20
```

20일 결과가 명확하면 여기서 끝낸다. `INCONCLUSIVE` 또는 extreme sample 부족일 때만 80일로 확대한다.
