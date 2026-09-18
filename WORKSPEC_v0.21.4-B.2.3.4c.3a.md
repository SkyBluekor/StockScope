# WORKSPEC v0.21.4-B.2.3.4c.3a
## Pre-Pool Strategy Search Audit — Top3 vs All Before Quick18

### 0. 실행 설정
- 모델: GPT-5.6 Sol
- 권장 추론 수준: Medium
- 목표: `Quick18` 후보가 만들어지기 **이전 단계**에서 Top3 전략 제한이 후보 자체를 누락시키는지 검증
- 원칙: Production Scanner 정책 변경 금지, 감사 코드만 추가/수정
- High 상향 조건: quick-score 산출 경로와 전략 current evaluation 경로를 분리해 재현하기 어려울 때만

---

## 1. 배경

기존 `B.2.3.4c.3` 감사는 다음 흐름으로 동작했다.

```text
시장 160종목
↓
Production _quick_current_candidate()
   ← 이미 Top3 전략 제한 적용
↓
Quick18 선택
↓
그 18종목 안에서 Top3 vs All 비교
```

그래서 확인된 것은:

> 이미 Top3 방식으로 선택된 후보 내부에서는 All 전략 평가가 전략 선택을 바꾸지 않았다.

실제 결과:
- 80개 평가일
- 전략 변경 0건
- Top3 밖 선택 0건
- Top5 변경 0건
- All 전략 평가 시간은 Top3 대비 약 3.1배

하지만 이 결과만으로는 다음 질문에 답할 수 없다.

> Top3 제한 때문에 `Quick18 후보에 들어오기 전` 좋은 종목이 탈락하고 있는가?

이번 작업은 이 누락을 바로잡는다.

---

## 2. 핵심 질문

시장 prefilter 통과 종목 각각에 대해:

```text
Top3 전략만 평가한 quick score
vs
전체 전략을 평가한 quick score
```

를 각각 계산하고,

그 결과 생성되는:

```text
Top18-A
vs
Top18-B
```

를 비교한다.

즉 이번 작업의 핵심은:

> **전략 평가 범위를 넓혔을 때 Quick18 후보군 자체가 바뀌는가?**

---

## 3. 비교 Variant

### BASELINE_PREPOOL_TOP3
현재 Production과 동일한 전략 제한.

```text
Market prefilter
→ 종목별 Top3 전략만 정밀 평가
→ quick score
→ 상위 18종목
→ current candidate
→ final ranking
```

### PREPOOL_ALL_STRATEGIES
동일한 종목과 전략 집합을 사용하되:

```text
Market prefilter
→ 종목별 전체 전략 정밀 평가
→ quick score
→ 상위 18종목
→ current candidate
→ final ranking
```

중요:
- Strategy scoring 공식 변경 금지
- Ranking 공식 변경 금지
- Quick limit 18 유지
- Market limit 160 유지
- 차이는 오직 **Quick18 선택 전에 전략 평가 범위를 Top3→All로 넓히는 것**

---

## 4. 고정 조건

Variant 간 아래는 모두 동일해야 한다.

- 평가일
- Universe
- Market limit = 160
- Quick limit = 18
- 데이터 fingerprint
- special exclusion
- liquidity filter
- strategy definitions
- thresholds
- current condition 계산
- Risk
- Entry / Stop / Invalidation
- Target1 / Target2
- final ranking policy
- Market Regime
- Historical Evidence 비개입
- 미래 outcome 계산 방식
- missing-data 처리

---

## 5. 평가일

가능하면 `B.2.3.4c.2`, `c.3`에서 사용한 동일 80개 날짜 재사용.

조건:
- 최소 60개
- 권장 80개
- 전체 유효 기간에 분산
- 미래 20거래일 outcome 확보 가능
- min-date-gap = 3 유지 가능하면 그대로 적용

목적:
이전 감사 결과와 직접 비교 가능하도록 한다.

---

## 6. 가장 중요한 측정 1 — Quick18 후보 교체

각 평가일마다:

```text
Top3 기반 Quick18
vs
All 기반 Quick18
```

비교.

기록:
- 동일 후보 수
- 교체 후보 수
- 새로 들어온 종목
- 빠진 종목
- overlap count
- replacement count

핵심 지표:
- quick_pool_changed_date_count
- quick_pool_changed_rate_pct
- average_replacements_per_changed_date
- max_replacements_per_date

---

## 7. 가장 중요한 측정 2 — 왜 후보가 바뀌었는가

새로 들어온 종목마다 반드시 추적:

- analysis_date
- ticker
- Top3 quick rank
- All quick rank
- Top3 quick score
- All quick score
- Top3 selected strategy
- All selected strategy
- All selected strategy initial rank
- tier
- risk
- missing condition count

그리고 빠진 종목도 동일하게 기록.

목적:
단순 순위 흔들림인지,
실제로 4위 이하 전략 평가 때문에 점수가 올라간 것인지 구분한다.

---

## 8. 가장 중요한 측정 3 — Outside Top3 Rescue

다음 조건을 만족하는 사례를 `rescued_candidate`로 정의한다.

```text
Top3 방식에서는 Quick18 밖
AND
All 방식에서는 Quick18 안
AND
All 선택 전략이 initial rank 4 이상
```

핵심 지표:
- rescued_candidate_count
- rescued_candidate_date_count
- rescued_candidate_rate
- rescued_candidate_top5_count
- rescued_candidate_ready_count

이 값이 0이면 Top3 제한이 pre-pool 병목일 가능성이 낮다.

---

## 9. 가장 중요한 측정 4 — Final Top5 영향

Quick18 후보군이 바뀐 뒤
기존 final ranking을 그대로 적용하여:

```text
Baseline Top5
vs
All-prepool Top5
```

비교.

기록:
- Top5 changed dates
- Top5 replacement count
- changed-date rate
- 새 Top5 진입 종목
- 빠진 Top5 종목

---

## 10. 미래 성과 비교

5D / 10D / 20D 기준:

- 평균 return
- 중앙값 return
- 평균 R
- 중앙값 R
- Target1-first
- Stop-first
- MFE
- MAE
- trimmed mean

특히 `rescued_candidate`에 대해서는 별도 paired 분석:

```text
새로 들어온 종목
-
밀려난 종목
```

기준으로:
- return delta
- R delta
- T1/Stop 차이
- MFE/MAE 차이

---

## 11. Quick Rank 이동 분석

전체 prefilter 통과 종목 중 전략 확장으로 순위가 얼마나 움직이는지 본다.

기록:
- mean absolute rank change
- median absolute rank change
- rank-up count
- rank-down count
- rank-up >= 5
- rank-up >= 10
- rank-up into Top18
- rank-down out of Top18

목적:
All 전략 평가가 실제로 후보 순위 구조를 바꾸는지 확인.

---

## 12. Strategy Rank 분포

All 방식에서 Quick18에 새로 진입한 종목들의
최종 선택 전략 initial rank 분포를 기록.

예:
```text
rank1: 3
rank2: 2
rank3: 1
rank4: 5
rank5: 4
rank6+: 2
```

이 정보로:
- Top3 충분
- Top5 정도면 충분
- All 필요
를 나중에 판단할 수 있다.

---

## 13. Runtime 비용

이번 감사는 160개 종목 전체에서 All 전략을 평가하므로
기존 c.3보다 더 무거울 수 있다.

반드시 기록:
- baseline prepool evaluation time
- all prepool evaluation time
- ratio
- 날짜당 총 runtime
- 평가 strategy count
- 총 current-evaluation count

진행 로그 필수:

```text
[ 1/80] 2023-06-07 OK poolΔ=2 rescued=1 3.82s
[ 2/80] 2023-06-20 OK poolΔ=0 rescued=0 3.61s
```

---

## 14. 판정 규칙

### KEEP_TOP3_PREPOOL
다음이면 Top3 유지:
- Quick18 후보 변경 거의 없음
- rescued_candidate 거의 없음
- Top5 영향 없음
- 미래 성과 개선 없음
- 비용만 크게 증가

### CONSIDER_EXPANDED_K
다음이면 Top3→Top5/Top6 후보:
- 후보 변경 반복 발생
- 유효 rescued 후보 존재
- 대부분 initial rank 4~5에 집중
- All까지 갈 필요는 없음

### CONSIDER_ALL_PREPOOL
다음 조건을 대부분 만족할 때:
- rescued 후보가 여러 시기에서 반복
- Top5까지 실제 진입
- paired 10D/20D R 개선
- Stop-first 악화 없음
- outlier 제거 후에도 방향 유지
- runtime 비용 감당 가능

### INCONCLUSIVE
- 후보 변경 사례는 있으나 성과 방향 불일치
- rescued 표본 부족
- 특정 날짜에만 몰림
- 데이터 부족

---

## 15. 구현 범위

권장 파일:

- `backend/app/backtest/scanner_quality/prepool_strategy_audit.py`
- `backend/tools/run_scanner_prepool_strategy_audit.py`
- 관련 테스트

가능하면 기존 공통 기능 재사용:
- temporal sampling
- future outcome
- trimmed stats
- fingerprint
- progress reporting
- result writers

기존 `c.3` 파일은 보존.
이번 감사가 별도 runner로 분리되는 편이 안전하다.

---

## 16. CLI 권장

Smoke:
```bash
python tools/run_scanner_prepool_strategy_audit.py --sample-size 10
```

Full:
```bash
python tools/run_scanner_prepool_strategy_audit.py --sample-size 80 --min-date-gap 3
```

---

## 17. 출력 위치

`backend/runtime/quality_audit/prepool_strategy/`

### JSON
`scanner-prepool-strategy-audit_<timestamp>.json`

### CSV 1
`scanner-prepool-strategy-signals_<timestamp>.csv`

### CSV 2
`scanner-prepool-strategy-pairs_<timestamp>.csv`

### Markdown
`scanner-prepool-strategy-summary_<timestamp>.md`

---

## 18. Summary 상단 필수 항목

```text
Valid dates
Quick18 changed dates
Quick18 change rate

Rescued candidates
Rescued Top5 candidates
Outside-Top3 rescue count

Top5 changed dates

5D / 10D / 20D delta
R delta
Stop delta

Runtime ratio

Verdict
```

---

## 19. 필수 테스트

### Test 1 — Production 불변
Audit 코드 추가 전/후 Production 결과 동일

### Test 2 — Variant Isolation
Top3 vs All 외 설정 동일

### Test 3 — Prepool All Coverage
Market160의 각 대상 종목에서 All 전략이 실제 평가되는지 확인

### Test 4 — Rescue Fixture
초기 4위 전략 때문에 quick rank가 20→10으로 올라가는 fixture에서
rescued candidate 정확히 탐지

### Test 5 — Quick18 Replacement
Top18 후보 교체 계산 정확성

### Test 6 — Final Top5 Propagation
Quick18 교체가 final Top5까지 반영되는지 확인

### Test 7 — Temporal Determinism
동일 설정이면 동일 평가일

### Test 8 — No Look-ahead
미래 데이터가 quick/current/rank에 사용되지 않음

### Test 9 — Runtime Recording
Top3 / All prepool 비용 별도 기록

---

## 20. 완료 조건

- [ ] 60~80개 분산 평가일 실행
- [ ] Market160 / Quick18 고정
- [ ] Quick18 이전 단계에서 Top3 vs All 비교
- [ ] 후보군 변경률 계산
- [ ] rescued candidate 탐지
- [ ] rescued 후보의 initial strategy rank 기록
- [ ] final Top5 변화 추적
- [ ] 5D/10D/20D paired outcome 비교
- [ ] runtime 비교
- [ ] deterministic / leakage 테스트 통과
- [ ] Production Scanner 불변
- [ ] KEEP_TOP3_PREPOOL / CONSIDER_EXPANDED_K / CONSIDER_ALL_PREPOOL / INCONCLUSIVE 판정

---

## 21. 이번 작업에서 하지 않는 것

- Production Top3 정책 변경
- Quick18→36 적용
- Market160 변경
- MA120 수정
- 중복 Strategy condition 수정
- Strategy weight 수정
- Ranking 공식 수정
- Market Regime 수정
- Historical Evidence 재투입
- ML 도입
- 성능 최적화

---

## 22. 다음 단계

### KEEP_TOP3_PREPOOL
Top3 병목 가능성 종료.
다음으로:
- MA120 입력 문제 검증
- 중복 Strategy condition 검증
- Ranking Entry-gap 우선권 감사

### CONSIDER_EXPANDED_K
Top5/Top6만 소규모 후속 감사

### CONSIDER_ALL_PREPOOL
별도 Production 정책 변경 명세 후 적용

### INCONCLUSIVE
표본 1회만 추가 확장 후 재판정

이번 단계의 목적은 오직:
**Top3 전략 제한이 Quick18 후보 자체를 누락시키는지 검증**
이다.
