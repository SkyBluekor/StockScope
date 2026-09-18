# WORKSPEC v0.21.4-B.2.3.4c.4a
## RS Dedup Counterfactual Audit Hotfix — Breakout Duplicate Weight 4 vs 8

### 0. 실행 설정
- 모델: GPT-5.6 Sol
- 권장 추론 수준: Medium
- 목표: `B.2.3.4c.4`에서 확인된 Breakout 상대강도 중복 결함의 **영향 측정 로직만 보정**
- 원칙: Production Strategy 정의는 절대 수정하지 않음. 이번 단계는 감사 코드 Hotfix + 재검증만 수행.
- High 상향 조건: 기존 감사 runner에서 실제 Breakout 조건별 weight/condition identity를 안전하게 분리하기 어려울 때만

---

## 1. 배경

`B.2.3.4c.4` Inspect 결과에서 두 가지 사실이 확인되었다.

### MA120
- `CONFIRMED_MA120_INPUT_DEFECT`
- 실제 Scanner snapshot 기술적 분석 window는 60 rows
- MA120 availability = 0%
- `60일선이 120일선 위` 조건이 2789 / 2789에서 unavailable
- local SMA120을 사용하면 1522건이 PASS 가능
- 10개 평가일 중 Quick18 변경 4일
- Top5 변경 0일

MA120 Counterfactual 경로는 정상 동작한 것으로 판단하며 이번 Hotfix의 직접 대상이 아니다.

### Breakout RS
Production Strategy 정의에서 실제 중복 조건이 확인되었다.

```python
("20일 업종 대비 상대강도 양호", 4, ...)
("20일 업종 대비 상대강도 양호", 8, ...)
```

두 조건은:
- condition label 동일
- predicate 동일
- runtime source 동일
- Scanner 경로에서 `relative_strength_sector_pct=None`
- sector RS가 없으면 market RS로 fallback

따라서 동일 신호가 반복 반영되는 구조는 실제 결함으로 확인됐다.

하지만 기존 `c.4` 감사에서 duplicate weight를 파싱하는 로직이 source 전체 숫자 후보 중 최소값을 선택해
실제 `4 / 8` 대신 `1.0`을 사용했다.

따라서 기존 RS Counterfactual의:
- Quick18 Δ
- Top5 Δ
- score Δ
- 성과 Δ

는 신뢰하지 않는다.

---

## 2. 이번 작업의 핵심 질문

이번 작업은 새로운 전략 연구가 아니다.

질문은 하나다.

> **Breakout에 중복된 두 RS 조건 중 하나만 제거했을 때 실제 Scanner 후보/Top5/성과가 어떻게 달라지는가?**

그리고 원래 의도가 weight 4인지 8인지 현재 코드만으로 단정하지 않는다.

따라서 두 경우를 모두 독립적으로 감사한다.

---

## 3. 비교 Variant

### BASELINE
현재 Production Breakout 정의 그대로.

```text
시장 RS             weight 6
업종 RS duplicate A weight 4
업종 RS duplicate B weight 8
```

### RS_KEEP_4
중복 두 조건 중 weight 8 조건만 감사 내부에서 제거.

```text
시장 RS             weight 6
업종 RS             weight 4
```

### RS_KEEP_8
중복 두 조건 중 weight 4 조건만 감사 내부에서 제거.

```text
시장 RS             weight 6
업종 RS             weight 8
```

중요:
- Production `strategy/engine.py`는 수정하지 않는다.
- 새 threshold/weight 생성 금지.
- 기존 4와 8만 사용.
- 두 Variant를 동시에 합치거나 평균내지 않는다.

---

## 4. Weight 식별 방식 수정

기존의 넓은 source-number 후보 수집 방식은 폐기한다.

정확한 Breakout condition tuple을 구조적으로 식별한다.

식별 조건:

```text
StrategyName.BREAKOUT
+
condition label == "20일 업종 대비 상대강도 양호"
```

그 아래 실제 tuple 2개를 순서와 weight까지 보존해 추출:

```text
duplicate[0].weight == 4
duplicate[1].weight == 8
```

가능하면 source AST 또는 실제 StrategyEvaluation condition 정의를 직접 사용한다.

정규식/문자열 파싱이 필요할 경우에도:
- Breakout 함수 범위 내부로 한정
- 정확한 label과 weight tuple만 추출
- 다른 파일의 숫자를 후보로 섞지 않음

---

## 5. Fail-Fast 검증

감사 실행 전에 반드시 다음을 확인한다.

```text
duplicate condition count == 2
weights == [4, 8]
label == "20일 업종 대비 상대강도 양호"
predicate source equivalent == true
```

하나라도 다르면 실행 중단.

예:

```text
RS audit aborted:
expected duplicate breakout RS weights [4, 8],
found [4]
```

잘못된 weight로 감사를 계속 진행하지 않는다.

---

## 6. Sector RS / Fallback 상태 분리

기존 Inspect 결과에서는 Scanner snapshot이:

```text
relative_strength_sector_pct = None
```

이었다.

이번 감사에서도 각 평가마다 다음을 기록한다.

- sector_rs_available
- sector_rs_value
- market_rs_value
- fallback_used
- duplicate_predicate_result_A
- duplicate_predicate_result_B

분류:

### SECTOR_AVAILABLE
실제 sector RS 존재.

### MARKET_FALLBACK
sector RS 없음 → market RS 사용.

### BOTH_MISSING
sector/market 모두 없음.

성과/후보 영향도 가능하면 위 그룹별로 별도 집계한다.

---

## 7. Score 보정 방식

Counterfactual은 실제 중복 condition 하나를 제거한 것과 동일해야 한다.

### RS_KEEP_4
```text
baseline breakout score
-
weight 8 condition contribution
```

### RS_KEEP_8
```text
baseline breakout score
-
weight 4 condition contribution
```

단순히 무조건 8점/4점을 빼면 안 된다.

해당 condition이 실제 PASS했을 때만 contribution을 제거한다.

FAIL이면 score 변화 0.

그리고:
- eligible
- passed count
- failed count
- readiness
- condition evidence

도 condition 제거에 맞춰 일관되게 재계산해야 한다.

---

## 8. Strategy 재선택

Breakout score만 바꾸고 끝내지 않는다.

각 종목에서 Counterfactual 후 전체 전략 비교를 다시 수행한다.

```text
기존 전체 전략 평가
↓
Breakout만 dedup 결과로 교체
↓
전략 재정렬
↓
selected strategy 재선택
↓
current readiness / Risk
↓
Quick score
↓
Quick18
↓
Final ranking
↓
Top5
```

즉 RS 중복 제거가:
- Breakout 자체 점수
- 초기 strategy rank
- 최종 selected strategy
- 후보 선정

까지 실제로 전파되게 한다.

---

## 9. 10일 Hotfix 재검증

첫 단계에서는 기존과 같은 10개 temporal-spread 날짜를 재사용한다.

목표:
- weight 파싱 보정 확인
- variant propagation 확인
- 잘못된 Counterfactual 재발 방지

출력에서 반드시 보여야 하는 항목:

```text
Detected duplicate weights: [4, 8]

RS_KEEP_4
Breakout score changed signals:
Strategy changed signals:
Quick18 changed dates:
Top5 changed dates:

RS_KEEP_8
Breakout score changed signals:
Strategy changed signals:
Quick18 changed dates:
Top5 changed dates:
```

이 10일 실행이 정상일 때만 80일 Full 진행.

---

## 10. 80일 Full Validation

10일 Hotfix 결과가 정상임을 확인한 뒤 실행.

조건:
- sample-size 80
- min-date-gap 3
- 이전 c.2 / c.3 / c.4와 같은 temporal-spread 원칙
- 미래 20 거래일 확보

MA120 Counterfactual도 같은 Full run에서 함께 유지한다.

단, 결과는 독립 분리:

```text
MA120_FIXED
RS_KEEP_4
RS_KEEP_8
```

결합 Variant는 만들지 않는다.

---

## 11. 측정 항목 — RS

각 Variant에 대해:

### 정의/실행
- duplicate weights detected
- dedup removed weight
- breakout evaluations
- breakout condition PASS count
- breakout score changed signals
- mean / median breakout score delta

### 전략 선택
- strategy changed signals
- breakout → other strategy
- other strategy → breakout
- initial strategy rank changes

### 후보
- Quick18 changed dates
- replacement count
- Final Top5 changed dates
- Top5 replacement count

### 상태
- READY/WATCH changes
- Risk changes
- missing condition count changes

### 미래 성과
- 5D / 10D / 20D mean return delta
- median return delta
- 5% trimmed mean delta
- mean/median R delta
- Target1-first delta
- Stop-first delta
- MFE / MAE delta

---

## 12. Paired Replacement 분석

Top5가 실제로 바뀐 날짜는 pair로 저장한다.

기록:

```text
analysis_date

baseline_out_code
counterfactual_in_code

baseline strategy
counterfactual strategy

removed_weight

5D return delta
10D return delta
20D return delta

5D R delta
10D R delta
20D R delta

Target1 / Stop event
```

RS_KEEP_4와 RS_KEEP_8 pair는 구분한다.

---

## 13. MA120 결과 유지

이번 Hotfix에서 MA120 감사 로직은 변경하지 않는다.

다만 80일 Full 시 아래 결과는 계속 기록한다.

- availability
- missing count
- wouldPass
- Quick18 changed dates
- Top5 changed dates
- 5D / 10D / 20D
- R / Stop delta

이번 작업에서 MA120 로직을 다시 설계하지 않는다.

---

## 14. 판정 규칙

### RS_DUPLICATION_NO_MATERIAL_IMPACT
두 Variant 모두:
- 전략 변경 거의 없음
- Quick18 영향 미미
- Top5 변화 거의 없음
- 성과 개선 근거 없음

### RS_KEEP_4_PREFERRED_CANDIDATE
80일 감사에서 RS_KEEP_4가:
- 여러 시기에서 안정적으로 개선
- 10D/20D return 및 R 개선
- Stop-first 악화 없음
- trimmed mean도 같은 방향
- 특정 outlier에 의존하지 않음

단, 이 판정도 Production 적용을 의미하지 않는다.

### RS_KEEP_8_PREFERRED_CANDIDATE
동일 기준으로 RS_KEEP_8이 더 안정적일 때.

### RS_DEDUP_MATERIAL_BUT_WEIGHT_UNCLEAR
중복 제거 자체는 도움이 되지만 KEEP_4 / KEEP_8 결과가 혼재할 때.

### RS_DEDUP_HARMFUL
중복 제거 후 후보/성과 품질이 일관되게 악화되는 경우.
이 경우에도 중복 정의 자체는 코드 결함으로 기록하되,
Production 변경 정책은 별도 설계 필요.

### INCONCLUSIVE
- 변경 표본 부족
- 기간별 방향 불일치
- 10일만 실행
- 데이터 부족

---

## 15. Overall Verdict

80일 Full에서는 MA120과 RS를 합쳐 다음 중 하나로 요약한다.

```text
MA120_DEFECT_MATERIAL
RS_DUPLICATION_MATERIAL
BOTH_MATERIAL
DEFECT_CONFIRMED_NO_MATERIAL_IMPACT
INCONCLUSIVE
```

단:
- `RS_KEEP_4` / `RS_KEEP_8`는 세부 recommendation candidate일 뿐
- Production 수정 결정은 별도 작업 명세에서 진행

---

## 16. 구현 범위

주요 변경 대상:

```text
backend/app/backtest/scanner_quality/strategy_integrity_audit.py
backend/tools/run_scanner_strategy_integrity_audit.py
backend/tests/test_scanner_strategy_integrity_audit.py
```

가능하면 기존 c.4 구조 유지.

새 runner를 만들지 않고 기존 runner를 Hotfix하는 것을 우선한다.

Production 파일:
```text
backend/app/strategy/engine.py
```
는 절대 수정하지 않는다.

---

## 17. CLI

### 10일 재검증
```bash
python tools/run_scanner_strategy_integrity_audit.py --mode inspect --sample-size 10 --min-date-gap 3
```

### 80일 Full
```bash
python tools/run_scanner_strategy_integrity_audit.py --mode full --sample-size 80 --min-date-gap 3
```

10일 결과 확인 전에는 Full 실행하지 않는다.

---

## 18. 출력 위치

기존 위치 유지:

```text
backend/runtime/quality_audit/strategy_integrity/
```

파일:

```text
scanner-strategy-integrity-audit_<timestamp>.json
scanner-strategy-integrity-signals_<timestamp>.csv
scanner-strategy-integrity-pairs_<timestamp>.csv
scanner-strategy-integrity-summary_<timestamp>.md
```

---

## 19. Summary 상단 필수 항목

```text
Valid dates

MA120 verdict
MA120 availability
MA120 Quick18 changed dates
MA120 Top5 changed dates

Breakout RS verdict
Detected duplicate weights: [4, 8]

RS_KEEP_4
- removed weight: 8
- strategy changed signals
- Quick18 changed dates
- Top5 changed dates

RS_KEEP_8
- removed weight: 4
- strategy changed signals
- Quick18 changed dates
- Top5 changed dates

Overall verdict
```

Full 모드에서는 추가:

```text
5D / 10D / 20D delta
R delta
Stop-first delta
```

---

## 20. 필수 테스트

### Test 1 — Exact Weight Detection
Breakout duplicate tuple에서 `[4, 8]` 정확히 탐지.

### Test 2 — Reject Wrong Weight
`[1, 4, 8]` 같은 broad numeric 후보를 사용하지 않음.

### Test 3 — Fail Fast
duplicate count != 2 또는 weights != [4,8]이면 실행 실패.

### Test 4 — PASS-only Score Removal
중복 condition PASS일 때만 4/8 contribution 제거.

### Test 5 — KEEP_4
weight 8만 제거되고 weight 4는 유지.

### Test 6 — KEEP_8
weight 4만 제거되고 weight 8은 유지.

### Test 7 — Strategy Reselect
Breakout score 감소 후 다른 전략이 선택되는 fixture 검증.

### Test 8 — Quick18 Propagation
전략 변화가 Quick18 교체로 이어지는 fixture 검증.

### Test 9 — Top5 Propagation
Quick18 교체가 Final Top5까지 전달되는 fixture 검증.

### Test 10 — MA120 Regression
기존 MA120 Counterfactual 결과가 Hotfix 전후 동일.

### Test 11 — Production Invariant
감사 코드 추가/수정 후 Production Scanner 결과 불변.

### Test 12 — No Look-ahead
미래 데이터 current 판단에 미사용.

---

## 21. 완료 조건

- [ ] 실제 Breakout duplicate weights `[4,8]` 정확히 식별
- [ ] 잘못된 `1.0` weight 파싱 제거
- [ ] RS_KEEP_4 구현
- [ ] RS_KEEP_8 구현
- [ ] PASS condition에만 contribution 제거
- [ ] 전략 재선택까지 propagation
- [ ] Quick18 / Top5 propagation
- [ ] 10일 Inspect 재실행 가능
- [ ] MA120 regression 유지
- [ ] Production 전략 정의 불변
- [ ] 테스트 통과
- [ ] 10일 정상 결과 확인 후 80일 Full 가능

---

## 22. 이번 작업에서 하지 않는 것

- Production Breakout duplicate 삭제
- weight 4 또는 8 중 하나를 Production 정답으로 확정
- Production MA120 수정
- MA120 + RS 결합 Variant
- Quick18→36 적용
- Market160 변경
- Ranking 변경
- Market Regime 변경
- Historical Evidence 재투입
- ML 도입
- Scanner 성능 최적화

---

## 23. 다음 단계

### 10일 Hotfix 정상
80일 Full 실행.

### 80일에서 MA120 material
별도 `MA120 Integrity Fix` 명세.

### 80일에서 RS material + KEEP_4/8 방향 명확
별도 `Breakout RS Dedup Fix` 명세.

### RS material but weight unclear
Strategy 설계 의도 검토 + 추가 소규모 weight policy audit.

### 둘 다 material
각 Production fix를 독립 적용한 뒤 마지막에 조합 회귀검증.

이번 단계의 원칙:

> **먼저 감사 도구부터 정확하게 고친 뒤, 그 결과로 Production 수정 여부를 결정한다.**
