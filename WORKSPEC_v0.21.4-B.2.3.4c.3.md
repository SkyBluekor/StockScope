# WORKSPEC v0.21.4-B.2.3.4c.3
## Strategy Search Audit — Top3 vs All

### 0. 실행 설정
- 모델: GPT-5.6 Sol
- 권장 추론 수준: Medium
- 목표: 현재 Scanner가 전략 점수 상위 3개만 정밀 평가하는 구조 때문에 더 적합한 전략을 놓치는지 검증
- 원칙: Production Scanner 정책 변경 금지, 감사/실험 코드만 추가 또는 확장
- High로 상향하는 조건: 전략 평가 경로가 여러 서비스/캐시/보조 로직으로 분기되어 동일 입력 통제가 어려울 때만

---

## 1. 배경

현재 Scanner는 종목별 전략 전체를 동일 수준으로 끝까지 비교하지 않는다.

현재 구조상:
1. 여러 전략에 대해 빠른 점수 계산
2. 점수 상위 3개 전략만 현재 조건 / Risk / 실행 가능성 평가
3. 그 안에서 최종 전략 선택
4. 선택된 전략 기준으로 후보 상태와 Ranking 계산

이 구조는 계산량을 줄이는 데는 유리하지만,
초기 전략 점수가 실제 READY 가능성 또는 미래 성과와 완전히 일치하지 않는다면
4위 이하 전략 중 더 적합한 전략을 놓칠 수 있다.

B.2.3.4c.2까지의 결과에서 Quick Pool 18→36은 개선 신호가 있었지만
전체 Top5가 달라진 날짜는 제한적이었다.

따라서 다음으로 더 큰 구조적 병목 가능성이 있는
`전략 Top3 제한`을 독립적으로 검증한다.

이번 작업의 질문은 하나다.

> **종목별 전략을 Top3만 정밀 평가하는 현재 방식이, 더 실행 가능하고 미래 성과가 좋은 전략을 놓치고 있는가?**

---

## 2. 핵심 가설

### H0
현재 상위 3개 전략 제한으로도 실질적으로 최적에 가까운 전략이 선택되며,
전체 전략을 평가해도 후보/전략/Top5 품질은 거의 달라지지 않는다.

### H1
4위 이하 전략 중 실제 조건/Risk 구조가 더 적합한 전략이 존재하며,
전체 전략을 평가하면 전략 선택 품질 또는 Top5 미래 성과가 개선된다.

---

## 3. 비교 Variant

이번에는 후보군 크기와 Ranking 정책을 고정한다.

### BASELINE_TOP3
- 현재 Production과 동일
- 초기 전략 평가 후 상위 3개만 current readiness / Risk 평가
- 나머지 정책은 기존 그대로

### ALL_STRATEGIES
- 동일한 종목
- 동일한 전략 집합
- 동일한 초기 strategy score 계산
- 단, Top3 제한 없이 모든 전략에 대해 current readiness / Risk 평가
- 최종 전략 선택 규칙은 기존 규칙 그대로 사용

중요:
`ALL_STRATEGIES`는 새로운 점수 공식을 만들지 않는다.
오직 기존 정밀 평가 대상을 3개에서 전체로 넓히는 실험이다.

---

## 4. 이번 실험에서 고정할 항목

Variant 간 아래 요소는 모두 동일해야 한다.

- 평가 날짜
- Universe
- Market limit
- Quick pool limit
- 데이터 fingerprint
- 전략 정의
- 전략 threshold
- current condition 계산
- Risk 계산
- Entry / Stop / Invalidation
- Target1 / Target2
- Ranking 정책
- Market Regime
- Historical Evidence 정책
- 미래 성과 평가 방식
- Missing-data 처리

이번 실험에서 바뀌는 것은 오직:

- `정밀 평가할 전략 수: 3개 vs 전체`

뿐이다.

---

## 5. Quick Pool 정책

B.2.3.4c.2에서 `Quick 36`이 개선 후보로 확인됐지만
아직 Production 정책으로 채택하지 않았다.

따라서 이번 감사의 Primary 비교는
**현재 Production과 동일한 Quick 18을 유지**한다.

이유:
- Strategy Top3 효과만 분리하기 위해
- Quick 36 효과와 Strategy All 효과가 섞이는 것을 방지하기 위해

Optional Secondary Run은 나중에 별도로:
- Quick36 + Top3
- Quick36 + All
조합을 검증할 수 있지만 이번 Primary 작업에는 포함하지 않는다.

---

## 6. 평가일 샘플링

B.2.3.4c.2와 동일한 temporal-spread 원칙을 재사용한다.

목표:
- 최소 60개 평가일
- 권장 80개 평가일
- 전체 유효 데이터 기간에 균등 분산
- 미래 20거래일 성과 확보 가능
- 인접 날짜 과도한 중복 방지

가능하면 B.2.3.4c.2의 동일 80개 날짜를 재사용한다.

이유:
- Quick Pool 감사와 직접 비교 가능
- 시장 환경 차이 최소화
- 동일 날짜에서 Strategy 제한 효과만 비교 가능

---

## 7. 가장 중요한 측정 1 — Top3 밖 전략의 구조적 누락

각 종목에서 전략 전체의 초기 순위를 기록한다.

ALL_STRATEGIES에서 최종 선택된 전략이
BASELINE_TOP3의 초기 Top3 밖이었다면 반드시 기록한다.

기록 항목:
- analysis_date
- ticker
- baseline_selected_strategy
- all_selected_strategy
- all_selected_initial_strategy_rank
- baseline strategy state
- all strategy state
- baseline Risk
- all Risk
- baseline missing condition count
- all missing condition count

핵심 지표:
- `outside_top3_selected_count`
- `outside_top3_selected_rate`
- Top3 밖 전략이 READY였던 비율
- Top3 밖 전략이 baseline 선택보다 더 좋은 tier였던 비율

---

## 8. 가장 중요한 측정 2 — 전략 선택 변화율

각 평가일별로:

- 전략이 바뀐 종목 수
- 후보 18개 중 전략 변경 비율
- Top5 내 전략 변경 종목 수
- READY/WATCH 상태 변화 종목 수
- Risk 상태 변화 종목 수

예:
```text
80개 날짜
전략 변경 발생 날짜: 31
Top5 전략 변경 날짜: 14
READY로 개선된 사례: 9
Risk 악화 사례: 2
```

---

## 9. 가장 중요한 측정 3 — Paired Strategy Outcome

동일 날짜/동일 종목에서 전략만 달라진 사례를 1:1로 비교한다.

각 pair에 대해:
- baseline strategy
- all-strategies strategy
- 5D / 10D / 20D forward return
- MFE / MAE
- Target1-first
- Stop-first
- R multiple

주의:
같은 종목이라 단순 종가 수익률은 동일할 수 있다.
따라서 Strategy 선택 효과는 특히:
- Entry 기준
- Invalidation
- Target
- Risk
- event R
차이에서 확인한다.

---

## 10. Top5 품질 비교

최종 Ranking 정책은 고정한 상태에서
전략 평가 범위만 바꿨을 때 Top5 품질을 비교한다.

### 5D / 10D / 20D
- 평균 forward return
- 중앙값 forward return
- 평균 R
- 중앙값 R
- Target1-first
- Stop-first
- MFE
- MAE

### 추가
- Top5 change rate
- 평균 교체 종목 수
- changed-date 성과 delta
- trimmed mean delta

---

## 11. Strategy별 선택 분포

BASELINE_TOP3와 ALL_STRATEGIES에서:

- 전략별 선택 횟수
- 전략별 READY 비율
- 전략별 WATCH 비율
- 전략별 평균 R
- 전략별 T1-first / Stop-first

를 비교한다.

목적:
특정 전략이 Top3 제한 때문에 구조적으로 거의 선택되지 않는지 확인.

예:
- `trend_following`이 초기 점수 구조 때문에 Top3에 거의 못 들어오는지
- `support_bounce`가 Risk 평가 후 실제로는 더 적합한데 초기에 잘리는지

---

## 12. Top3 초기 점수의 품질 검증

초기 strategy score 순위 자체가
최종 readiness / Risk / 미래 성과와 얼마나 연결되는지 본다.

측정:
- initial strategy rank vs final tier
- initial strategy rank vs missing condition count
- initial strategy rank vs Risk quality
- initial strategy rank vs event R

목적:
Top3 제한이 합리적인지 검증.

만약 4~10위 전략이 거의 항상 열위라면 Top3 유지 근거가 된다.
반대로 낮은 초기 순위 전략이 자주 READY로 역전되면 Top3 제한은 약점이다.

---

## 13. 결과 안정성

평균 하나로 결론 내리지 않는다.

반드시 확인:
- 평균
- 중앙값
- 날짜별 개선/악화 비율
- 5% trimmed mean
- 5D/10D/20D 방향 일치 여부
- 전략 변경 사례의 paired 결과
- 특정 전략 하나가 전체 개선을 독점하는지 여부

---

## 14. Runtime 비용

ALL_STRATEGIES는 계산량이 늘 수 있으므로 반드시 기록한다.

Variant별:
- current evaluation 평균 시간
- 날짜당 총 runtime
- Top3 대비 All 배수
- 전략 평가 건수

판정 시 품질 개선 대비 비용도 함께 본다.

예:
- 품질 +0.3%p, runtime +5% → 검토 가치 있음
- 품질 +0.02%p, runtime +200% → 채택 근거 약함

---

## 15. 판정 규칙

### KEEP_TOP3
다음에 가까우면 현재 Top3 유지:
- 전략 변경률이 매우 낮음
- Top3 밖 전략이 READY로 역전되는 사례가 드묾
- Top5 품질 개선 없음
- R / Stop 결과 개선 없음
- 계산비용만 증가

### CONSIDER_ALL
다음 조건을 대부분 만족할 때:
- Top3 밖 전략이 반복적으로 최종 선택됨
- 그 전략이 readiness / Risk 구조에서 더 우수
- 여러 기간에서 paired R 개선
- Top5 10D/20D 품질 개선
- Stop-first 악화 없음
- 특정 몇 날짜/outlier에만 의존하지 않음
- 계산비용이 감당 가능

### CONSIDER_EXPANDED_K
All이 유의미하지만 비용이 너무 크고,
실제 유효 전략이 주로 4~5위에 몰려 있다면:

- Top3 → Top5
- Top3 → Top6

같은 중간 정책을 후속 실험 후보로 제안한다.

### INCONCLUSIVE
- 전략 변경 사례 부족
- 성과 방향 불일치
- 특정 전략 하나에 결과 집중
- 데이터 부족

---

## 16. 구현 범위

기존 quality audit framework를 확장한다.

권장:
- `backend/app/backtest/scanner_quality/strategy_search_audit.py`
- 기존 공통 outcome / temporal sampling 유틸 재사용
- `backend/tools/run_scanner_strategy_audit.py`
- 관련 테스트

가능하면 B.2.3.4c.1/c.2에서 만든:
- temporal sampling
- forward outcome
- trimmed stats
- result writer
를 재사용해 중복 구현을 피한다.

Production Scanner 기본 동작은 변경하지 않는다.

---

## 17. CLI 권장

```bash
python tools/run_scanner_strategy_audit.py --sample-size 80 --min-date-gap 3
```

필요한 경우:
```bash
python tools/run_scanner_strategy_audit.py --sample-size 20
```

Smoke Test 지원.

---

## 18. 출력물

권장 위치:

`backend/runtime/quality_audit/strategy_search/`

### JSON
`scanner-strategy-audit_<timestamp>.json`

포함:
- 평가일
- 데이터 fingerprint
- Variant 설정
- 종목별 전략 초기 순위
- baseline/all 선택 전략
- strategy change
- readiness / Risk
- Top5 metrics
- paired metrics
- runtime
- verdict

### CSV 1
`scanner-strategy-signals_<timestamp>.csv`

행:
- analysis_date
- ticker
- variant
- selected_strategy
- initial_strategy_rank
- tier
- risk
- missing conditions
- rank
- 5D/10D/20D
- event R

### CSV 2
`scanner-strategy-pairs_<timestamp>.csv`

전략이 달라진 동일 종목 pair 전용.

### Markdown
`scanner-strategy-summary_<timestamp>.md`

최상단:
- Valid dates
- Strategy changed dates
- Strategy changed signals
- Outside Top3 selected count
- Top5 change rate
- 5D/10D/20D delta
- R delta
- Runtime ratio
- Verdict

---

## 19. 필수 테스트

### Test 1 — Production 불변
Audit 추가 전/후 Production Scanner 결과 동일

### Test 2 — Variant Isolation
Top3 vs All 외 다른 설정 동일

### Test 3 — All Strategy Coverage
fixture에서 모든 전략이 current evaluation 대상이 되는지 확인

### Test 4 — Outside Top3 Detection
초기 4위 전략이 최종 선택되는 fixture에서 정확히 탐지

### Test 5 — Paired Strategy Comparison
동일 종목/다른 전략 pair 계산 정확성

### Test 6 — Temporal Sampling Determinism
동일 설정이면 동일 평가일

### Test 7 — No Look-ahead
미래 데이터 Scanner 입력 금지

### Test 8 — Runtime Recording
Top3 / All 시간 별도 기록

---

## 20. 완료 조건

- [ ] 60~80개 분산 평가일 실행 가능
- [ ] Top3 vs All만 독립 비교
- [ ] Top3 밖 최종 선택 전략 탐지 가능
- [ ] 전략 변경률 계산 가능
- [ ] READY/WATCH/Risk 변화 추적 가능
- [ ] 동일 종목 paired outcome 비교 가능
- [ ] Top5 5D/10D/20D 성과 비교 가능
- [ ] 전략별 선택 분포 비교 가능
- [ ] 초기 strategy rank 품질 분석 가능
- [ ] runtime 비용 비교 가능
- [ ] deterministic/leakage 테스트 통과
- [ ] Production Scanner 결과 변경 없음
- [ ] KEEP_TOP3 / CONSIDER_ALL / CONSIDER_EXPANDED_K / INCONCLUSIVE 중 판정 가능

---

## 21. 이번 작업에서 하지 않는 것

- Production Top3 정책 변경
- Quick 18→36 적용
- Market 160 변경
- MA120 입력 수정
- 중복 전략 condition 수정
- Strategy weight 수정
- Ranking 공식 수정
- Market Regime 수정
- Historical Evidence 재투입
- ML 모델 도입

---

## 22. 다음 단계

### KEEP_TOP3
전략 검색 폭은 유지하고 다음 문제로 이동:
- MA120 입력 / 중복 condition 감사
또는
- Ranking Entry-gap 우선권 감사

### CONSIDER_ALL
바로 Production 수정하지 않고
별도 `Strategy Search Policy Change` 명세 작성 후 적용

### CONSIDER_EXPANDED_K
Top5 / Top6 등 중간 K를 소규모 후속 감사

### INCONCLUSIVE
표본을 한 번만 추가 확장하고 재판정

이번 작업도:
**감사 → 결과 → 정책 결정**
순서를 유지한다.
