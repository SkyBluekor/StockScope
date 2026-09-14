# v0.20.2.4 Condition / Decision Consistency

결과 설명의 기준을 다음 한 방향으로 고정합니다.

`StrategyEvaluation reasons/unmet` → `condition state` → `passed/missing/total` → `current decision` → `user-facing recommendation`

## 판정 우선순위
1. 과거 표본 부족
2. 현재 전략 조건 부족
3. 전략 조건 완료 후 Risk 차단/경고
4. 진입 후보

조건 부족과 Risk 경고가 동시에 존재하면 조건 부족을 주원인으로, Risk를 보조 경고로 표시합니다.

## 불변식
- `total = passed + missing`
- `len(conditions) = total`
- `len(passed_details) = passed`
- `len(missing_details) = missing`

엔진 집계와 상세 목록이 다르면 consistency 오류를 노출하고 해당 결과를 진입 판단에 사용하지 않도록 안내합니다.
