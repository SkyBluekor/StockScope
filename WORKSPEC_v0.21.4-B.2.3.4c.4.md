# WORKSPEC v0.21.4-B.2.3.4c.4
## Strategy Definition Integrity Audit — MA120 Input & Breakout RS Duplication

### 0. 실행 설정
- 모델: GPT-5.6 Sol
- 권장 추론 수준: Medium
- 목표: Astra가 지적했던 두 가지 전략 정의 문제를 **현재 코드 기준으로 사실 여부부터 검증**하고, 실제 문제일 경우 Scanner 품질에 미치는 영향을 감사한다.
- 원칙: Production 전략/점수/조건 변경 금지. 이번 단계는 `검증 → 영향 측정`까지만 수행.
- High 상향 조건: 전략 입력 생성 경로가 여러 계층으로 분리되어 MA/RS 값의 실제 출처를 추적하기 어려울 때만.

---

## 1. 이번 작업의 핵심 질문

이번에는 아래 두 주장을 그대로 믿지 않는다.

### 가설 A — MA120 입력 부족
Astra 주장:
- 전략 입력 snapshot이 약 60개 봉만 사용한다.
- 그 결과 `ma120`이 계산되지 않거나 `None`이 된다.
- 따라서 `ma60 > ma120` 같은 장기 추세 조건이 사실상 통과 불가능할 수 있다.

### 가설 B — Breakout Relative Strength 중복
Astra 주장:
- Breakout 전략에서 유사한 sector relative-strength 조건이 중복으로 존재한다.
- 서로 다른 weight가 붙어 동일 신호가 두 번 점수에 반영될 가능성이 있다.
- sector RS가 없을 때 market RS로 fallback되면 사실상 같은 값이 중복 반영될 가능성이 있다.

이번 작업은 먼저:

> **현재 코드가 실제로 그렇게 동작하는가?**

를 확인한다.

그리고 사실이라면:

> **그 문제가 전략 선택/Quick18/Top5 품질에 실제 영향을 주는가?**

를 별도로 측정한다.

---

## 2. 작업 범위

이번 감사에는 두 파트가 있다.

### Part A — Static / Runtime Integrity Check
코드와 실제 runtime 값을 추적해 사실관계 확인.

### Part B — Counterfactual Impact Audit
문제가 확인된 항목에 한해서만 감사용 보정 variant를 만들어 영향 측정.

중요:
- Part A에서 문제가 아니라고 확인되면 해당 Part B 실험은 수행하지 않는다.
- 확인되지 않은 가설을 근거로 코드를 바꾸지 않는다.

---

# PART A — 사실관계 검증

## 3. MA120 입력 경로 추적

다음 흐름을 실제 코드에서 추적한다.

```text
Market history
→ signal/history slice
→ strategy input/context
→ indicator calculation
→ strategy condition
→ current readiness
→ quick score / selected strategy
```

확인 항목:

- 전략 입력에 실제 몇 개의 bar가 전달되는가
- `ma20`, `ma60`, `ma120` 각각 어느 단계에서 계산되는가
- MA120 계산 최소 row 수
- row 부족 시 값이:
  - None
  - 0
  - fallback
  - 계산 생략
  중 무엇인지
- `trend_following` 및 MA120을 참조하는 모든 전략/조건 목록
- MA120이 None일 때 condition 결과
- 최근 실제 Scanner 후보에서 MA120 availability 비율

반드시 코드 위치와 runtime 관측을 둘 다 기록한다.

---

## 4. MA120 문제 판정

### CONFIRMED_MA120_INPUT_DEFECT
다음이 모두 또는 대부분 사실일 때:
- MA120 조건이 존재
- 실제 입력 window가 MA120 계산에 부족
- 다수 종목에서 MA120이 unavailable
- unavailable 때문에 조건이 구조적으로 FAIL/무효화됨

### MA120_OK
- 충분한 history가 전달됨
- 또는 MA120은 별도 full-history context에서 정상 계산됨
- 또는 unavailable이 전략 판단을 막지 않음

### MA120_PARTIAL
- 특정 경로/날짜/종목에서만 부족
- 전체 구조적 문제는 아님

---

## 5. Breakout RS 정의 추적

Breakout 전략의 모든 조건을 실제 코드에서 수집한다.

각 condition마다 기록:

- condition id / label
- metric key
- source value
- comparison rule
- weight
- quick-score 기여
- readiness 기여
- fallback source

특히 아래를 확인:

```text
sector_relative_strength
market_relative_strength
relative_strength
sector_rs fallback → market_rs
```

같은 값 또는 동일 의미의 값이 여러 condition에 들어가는지 본다.

---

## 6. RS 중복 판정

### CONFIRMED_RS_DUPLICATION
다음이 확인될 때:
- 둘 이상의 condition이 실질적으로 같은 runtime 값을 사용
- 두 condition 모두 점수 또는 readiness에 독립 기여
- 동일 신호가 중복 weight로 반영됨

### RS_DISTINCT
- 이름은 비슷하지만 서로 다른 데이터/조건
- 각각 독립 의미가 있음

### RS_FALLBACK_DUPLICATION
- sector RS가 존재할 때는 별개지만
- sector RS unavailable 시 둘 다 market RS를 사용하여 중복되는 경우

이 세 경우를 명확히 구분한다.

---

# PART B — 영향 감사

## 7. MA120 Counterfactual Variant

Part A에서 MA120 문제가 확인된 경우에만 실행.

### BASELINE
현재 Production과 동일.

### MA120_FIXED_AUDIT
Production 코드는 수정하지 않고 감사 내부에서만:

- 충분한 history window 사용
- 현재 indicator 계산 공식을 그대로 사용
- MA120만 정상 계산 가능하게 함
- 전략 조건/weight/Ranking은 변경 금지

비교:

```text
Baseline
vs
MA120-fixed audit
```

---

## 8. MA120 영향 측정

측정 항목:

- MA120 unavailable rate
- MA120 조건 PASS/FAIL 변화
- 전략별 selection 변화
- trend_following 선택 변화
- Quick18 변화 날짜
- Quick18 replacement count
- Final Top5 변화 날짜
- READY/WATCH 변화
- Risk 변화
- 5D/10D/20D return
- R
- Target1-first
- Stop-first
- MFE/MAE

특히:

```text
MA120 복구
→ 전략 상태 개선
→ Quick18 진입
→ Final Top5 진입
```

흐름이 실제로 발생하는지 추적한다.

---

## 9. RS Counterfactual Variant

Part A에서 중복이 확인된 경우에만 실행.

### BASELINE
현재 Production Breakout 정의.

### RS_DEDUP_AUDIT
감사 내부에서만:

- 중복 condition 중 하나를 비활성화하거나
- 중복 weight를 한 번만 반영

단:
- 어떤 condition을 제거할지는 Part A 결과로 결정
- 새로운 threshold/weight를 만들지 않는다
- 가장 보수적으로 "동일 신호의 중복 반영 제거"만 수행

---

## 10. RS 영향 측정

측정 항목:

- Breakout quick score 변화
- Breakout initial strategy rank 변화
- Breakout selection count 변화
- 다른 전략으로 교체된 종목 수
- Quick18 변화
- Final Top5 변화
- READY/WATCH 변화
- Risk 변화
- 5D/10D/20D
- R
- Target1-first
- Stop-first
- MFE/MAE

추가:

```text
sector RS 정상 존재 시
vs
sector RS fallback 시
```

를 분리해 본다.

이유:
중복 문제가 fallback 상황에만 발생할 수도 있기 때문.

---

## 11. 결합 실험 금지

이번 단계에서는:

```text
MA120_FIXED + RS_DEDUP
```

결합 variant를 기본 실행하지 않는다.

먼저 각각 독립 영향부터 본다.

둘 다 실제 영향이 확인될 경우에만 후속 작업에서 조합 검증.

---

## 12. 평가일

가능하면 이전 감사와 동일한 80개 temporal-spread 날짜 사용.

조건:
- 최소 60
- 권장 80
- min-date-gap 3
- 미래 20거래일 확보
- 동일 데이터 fingerprint 사용

정적 검증은 전체 코드 기준,
영향 감사는 동일 날짜 기준으로 수행.

---

## 13. 출력 결과 — Integrity Report

JSON/Markdown에 반드시 아래를 포함:

### MA120
- actual input window
- MA120 required rows
- MA120 availability rate
- affected strategies
- affected conditions
- verdict

### Breakout RS
- condition 목록
- metric source
- weight
- fallback source
- duplicate 여부
- verdict

이 부분은 성과 결과보다 먼저 보여야 한다.

---

## 14. 출력 결과 — Impact Report

문제가 확인된 경우에만:

### MA120
- strategy changes
- Quick18 changes
- Top5 changes
- 5/10/20D delta
- R delta
- Stop delta

### RS
- breakout score delta
- strategy changes
- Quick18 changes
- Top5 changes
- 5/10/20D delta
- R delta
- Stop delta

---

## 15. 판정 체계

### NO_INTEGRITY_DEFECT
두 주장 모두 현재 코드에서 사실이 아님.

### DEFECT_CONFIRMED_NO_MATERIAL_IMPACT
문제는 존재하지만:
- 후보 선택
- Top5
- 성과
에 유의미한 영향 없음.

### MA120_DEFECT_MATERIAL
MA120 문제로 실제 후보/전략 품질 변화 발생.

### RS_DUPLICATION_MATERIAL
RS 중복으로 실제 후보/전략 품질 변화 발생.

### BOTH_MATERIAL
둘 다 실제 영향 있음.

### INCONCLUSIVE
사실관계는 확인됐지만 영향 표본이 너무 적거나 방향 불일치.

---

## 16. 구현 권장 구조

권장 파일:

```text
backend/app/backtest/scanner_quality/
    strategy_integrity_audit.py

backend/tools/
    run_scanner_strategy_integrity_audit.py
```

가능하면 기존 공통 기능 재사용:

- temporal sampling
- future outcome
- trimmed stats
- fingerprint
- progress callback
- result writer

Production strategy 파일 자체는 수정하지 않는다.

---

## 17. CLI 권장

Static + smoke:

```bash
python tools/run_scanner_strategy_integrity_audit.py --mode inspect --sample-size 10
```

Full:

```bash
python tools/run_scanner_strategy_integrity_audit.py --mode full --sample-size 80 --min-date-gap 3
```

Part A에서 결함이 없으면 해당 counterfactual은 자동 skip.

---

## 18. 출력 위치

```text
backend/runtime/quality_audit/strategy_integrity/
```

생성 파일:

```text
scanner-strategy-integrity-audit_<timestamp>.json
scanner-strategy-integrity-signals_<timestamp>.csv
scanner-strategy-integrity-pairs_<timestamp>.csv
scanner-strategy-integrity-summary_<timestamp>.md
```

---

## 19. Summary 최상단

```text
Valid dates

MA120 verdict
Actual strategy history window
MA120 availability rate
MA120 affected strategies

Breakout RS verdict
Duplicate/fallback duplicate count

MA120 Quick18 changed dates
MA120 Top5 changed dates

RS Quick18 changed dates
RS Top5 changed dates

Runtime
Overall verdict
```

---

## 20. 필수 테스트

### Test 1 — Production 불변
감사 코드 추가 전/후 Production Scanner 결과 동일.

### Test 2 — MA120 Window Detection
60-row fixture와 130-row fixture에서 availability 판정 정확성.

### Test 3 — MA120 Condition Propagation
MA120 None/available에 따라 조건 결과가 기대대로 변하는지 확인.

### Test 4 — RS Duplicate Detection
동일 metric source + 동일 runtime value가 두 조건에 들어가는 fixture 탐지.

### Test 5 — RS Distinct Detection
이름은 비슷하지만 실제 값이 다른 경우 중복으로 오판하지 않음.

### Test 6 — Fallback Duplication
sector RS None → market RS fallback 시 중복 탐지.

### Test 7 — Variant Isolation
MA120 실험은 MA120 입력만 변경.
RS 실험은 중복 반영만 제거.

### Test 8 — No Look-ahead
미래 데이터가 current 판단에 사용되지 않음.

### Test 9 — Temporal Determinism
같은 설정이면 같은 평가일.

### Test 10 — Output Integrity
Part A 결과와 Part B 결과가 별도 섹션으로 기록됨.

---

## 21. 완료 조건

- [ ] 실제 MA120 입력 경로 확인
- [ ] 실제 history window 확인
- [ ] MA120 availability 측정
- [ ] MA120 관련 전략/조건 목록 확보
- [ ] Breakout RS 조건 전체 추적
- [ ] 실제 metric source / fallback 추적
- [ ] 중복 여부 판정
- [ ] 결함이 있을 때만 counterfactual 실행
- [ ] Quick18 / Top5 영향 측정
- [ ] 5D/10D/20D 및 R 영향 측정
- [ ] Production 결과 불변
- [ ] 최종 integrity verdict 생성

---

## 22. 이번 작업에서 하지 않는 것

- Production MA120 수정
- Production Breakout condition 삭제
- Strategy weight 재설계
- 새로운 threshold 도입
- Quick18→36 적용
- Market160 변경
- Ranking 수정
- Market Regime 수정
- Historical Evidence 재투입
- ML 도입
- Scanner 속도 최적화

---

## 23. 다음 단계

### NO_INTEGRITY_DEFECT
다음으로 Ranking Entry-gap 우선권 감사.

### DEFECT_CONFIRMED_NO_MATERIAL_IMPACT
결함은 기록하되 Production 변경 우선순위 낮춤.

### MA120_DEFECT_MATERIAL
별도 `MA120 Integrity Fix` 명세 후 Production 수정.

### RS_DUPLICATION_MATERIAL
별도 `Breakout RS Dedup Fix` 명세 후 Production 수정.

### BOTH_MATERIAL
각 수정안을 독립 적용한 뒤 마지막에 조합 회귀 검증.

### INCONCLUSIVE
표본을 1회만 추가 확장.

이번 단계의 핵심 원칙:

> **Astra의 주장을 믿고 고치는 것이 아니라, 현재 코드에서 실제인지 확인하고 영향까지 증명한 뒤 고친다.**
