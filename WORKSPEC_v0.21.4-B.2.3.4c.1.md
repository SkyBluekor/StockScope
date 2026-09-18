# WORKSPEC v0.21.4-B.2.3.4c.1
## Early Candidate Pruning Audit

### 0. 실행 설정
- 모델: GPT-5.6 Sol
- 권장 추론 수준: Medium
- 원칙: 최소 범위 수정, Production Scanner 동작 변경 금지, 실험/감사 코드만 추가
- High로 상향하는 조건: 현재 후보 축소 경로가 문서와 다르거나, 후보군 생성 로직이 여러 경로로 분기되어 원인 분리가 어려울 때만

---

## 1. 작업 목적

현재 Scanner는 전체 종목을 바로 정밀 평가하지 않고, 여러 단계에서 후보를 선제 축소한다.

현재 확인된 핵심 흐름:

1. 전체 종목 Universe
2. 시장별 거래대금 상위 약 160개
3. 간이 평가(quick score)
4. 전체 상위 약 18개
5. 현재 조건 / Risk / Strategy 평가
6. 최종 Ranking

이번 작업의 목적은 다음 질문 하나만 검증하는 것이다.

> **좋은 종목이 최종 Ranking 전에 후보 축소 단계에서 탈락하고 있는가?**

이번 단계에서는 Ranking 공식, Strategy 선택, Risk, Entry/Stop/Target 계산을 수정하지 않는다.

---

## 2. 핵심 가설

### H0
현재의 `시장별 160개 → quick score 상위 18개` 제한은 최종 Top 5 품질에 실질적인 손실을 만들지 않는다.

### H1
현재의 선제 후보 제한 때문에 이후 실제 성과가 더 좋았던 종목이 최종 평가 전에 탈락하며, 후보군을 넓히면 Top 5 품질이 개선될 가능성이 있다.

---

## 3. 실험 범위

Production Scanner는 그대로 유지하고, 별도 Audit Runner에서 동일 날짜/동일 데이터로 아래 Variant를 재생한다.

### Baseline
- 시장별 선별: 현재 값 유지
- quick 후보 제한: 현재 값 유지

### Variant A — Market Pre-filter 완화
- 시장별 선별 범위를 확대
- quick 후보 제한은 기존 값 유지
- 목적: `시장별 160개` 단계에서 좋은 종목을 잃는지 확인

### Variant B — Quick Candidate 제한 완화
- 시장별 선별은 기존 값 유지
- quick 후보 제한만 확대
- 목적: `상위 18개` 단계에서 좋은 종목을 잃는지 확인

### Variant C — 두 제한 모두 완화
- 시장별 선별 확대
- quick 후보 제한 확대
- 목적: 두 병목의 결합 효과 확인

### 중요
정확한 확대 수치는 여러 값을 광범위하게 탐색하지 않는다.
초기 감사에서는 소수의 사전 고정 값만 사용한다.

예:
- Market limit: 160 → 320
- Quick candidate limit: 18 → 36

필요하면 Stage 2에서만 추가 확장한다.

---

## 4. 비교 시 반드시 고정할 항목

Variant 간 아래 요소는 완전히 동일해야 한다.

- 분석 기준일
- Universe
- Market Store 데이터
- 데이터 fingerprint
- Strategy 정의
- Strategy threshold
- Risk
- Entry
- Stop / Invalidation
- Target1 / Target2
- Current conditions
- Ranking 정책
- 거래 비용 가정
- 미래 성과 평가 방식
- Missing-data 처리

즉 이번 실험에서 바뀌는 것은 오직:

- 시장별 초기 후보 수
- quick 후보 수

뿐이다.

---

## 5. Walk-forward 검증

과거 각 평가일 `t`에 대해:

1. `t`일까지 이용 가능했던 데이터만 Scanner 입력으로 사용
2. 각 Variant의 후보군과 최종 Ranking 생성
3. `t+1` 이후 데이터는 오직 성과 평가에만 사용
4. 미래 데이터가 후보 생성 / Strategy / Ranking에 들어가면 해당 실행은 실패 처리

### 평가 Horizon
- 5 거래일
- 10 거래일
- 20 거래일

### Price-plan 평가
가능한 경우 기존 StockScope의 동일한 Entry/Stop/Target 정책을 사용해:

- Target1 before Stop
- Target2 before Stop
- Stop before Target1
- R multiple

을 계산한다.

---

## 6. 이번 작업에서 가장 중요한 측정값

### A. Candidate Recall Loss
Baseline에서 잘렸지만 확대 Variant에서는 살아남은 종목 중,
미래 성과 상위권 종목의 수를 측정한다.

예:
- 확대 후보군 미래 수익 상위 10% 중 Baseline이 놓친 비율
- 확대 후보군에서 Target1에 도달했지만 Baseline에서 탈락한 종목 수

이 값이 높으면 초기 pruning에 정보 손실이 있다는 의미다.

### B. Top 5 품질
각 Variant의 최종 Top 5에 대해:

- 평균 / 중앙값 5D, 10D, 20D forward return
- 평균 R
- Expectancy
- Target1-before-Stop 비율
- Stop-before-Target1 비율
- MFE / MAE

### C. Ranking 보존 여부
후보군만 넓혔을 때:

- 기존 Top 5가 얼마나 유지되는지
- 새롭게 진입한 종목이 기존 Top 5보다 실제 성과가 좋았는지

### D. 비용
- Variant별 평가 종목 수
- 실행 시간
- 메모리 사용량(가능한 범위)
- 후보 1개 추가당 계산 비용

이번 작업의 Primary 목표는 품질이지만,
후보군 확대가 비현실적으로 비싸지 않은지도 함께 기록한다.

---

## 7. 결과 판정 규칙

단일 날짜의 결과로 결론 내리지 않는다.

최소 조건:

- 동일 데이터셋
- 여러 과거 평가일
- 충분한 signal 수
- 날짜 단위 집계

### 판정 예

#### KEEP_BASELINE
후보군 확대가:
- Candidate recall을 거의 개선하지 못하고
- Top 5 미래 성과도 개선하지 못하며
- 계산 비용만 증가

#### EXPAND_MARKET_FILTER
Variant A가 반복적으로 개선되고 Variant B 효과는 미미

#### EXPAND_QUICK_POOL
Variant B가 반복적으로 개선되고 Variant A 효과는 미미

#### EXPAND_BOTH
Variant C가 일관된 개선을 보이며 비용도 감당 가능

#### INCONCLUSIVE
차이가 작거나 기간별 결과가 불안정

---

## 8. 구현 범위

### 신규 권장 파일

- `backend/app/backtest/scanner_quality/early_pruning_audit.py`
  - Baseline/Variant 실행
  - 후보 단계별 trace 수집

- `backend/app/backtest/scanner_quality/models.py`
  - 실험 결과 구조

- `backend/tools/run_scanner_pruning_audit.py`
  - CLI 실행기

- `backend/tests/test_scanner_pruning_audit.py`
  - 결정론 / leakage / variant-isolation 테스트

구조가 현재 저장소와 맞지 않으면 기존 디렉터리 규칙을 우선한다.

### 기존 파일 수정
최소화한다.

필요 시 `scanner.py`에서:
- 기존 후보 축소 경로를 재사용 가능한 내부 함수로 추출하거나
- audit hook을 추가

단, Production 기본값과 동작은 변경하지 않는다.

---

## 9. 출력물

권장:

`runtime/quality_audit/pruning/`

### JSON
`scanner-pruning-audit_<generated_at>.json`

포함:
- 코드/Scanner version
- Git commit
- 데이터 fingerprint
- 평가일 목록
- Variant 설정
- 단계별 후보 수
- Candidate recall
- Top5 지표
- Runtime

### CSV
`scanner-pruning-signals_<generated_at>.csv`

행 단위:
- analysis_date
- variant
- rank
- ticker
- strategy
- current state
- forward 5/10/20D
- MFE
- MAE
- T1/Stop 결과
- baseline 포함 여부
- 어느 pruning 단계에서 탈락했는지

### Markdown
`scanner-pruning-summary_<generated_at>.md`

사람이 바로 읽을 수 있도록:
- Baseline vs A/B/C
- Candidate loss
- Top5 변화
- 실행비용
- 결론

---

## 10. 반드시 포함할 추적 정보

각 종목에 대해 최소한 아래를 기록한다.

- 전체 Universe 포함 여부
- Market pre-filter 통과 여부
- quick pool 통과 여부
- final evaluation 진입 여부
- 최종 rank
- 탈락 단계
- 탈락 당시 quick score / trade value 등 해당 단계 판단값

그래야 나중에 단순히 “탈락했다”가 아니라
**왜 탈락했는지** 역추적할 수 있다.

---

## 11. 테스트

### 필수 테스트 1 — Production 불변
Audit 기능 추가 전/후 동일 입력의 Production Scanner 결과가 동일해야 한다.

### 필수 테스트 2 — Variant Isolation
Variant A는 market limit만 변경되어야 한다.
Variant B는 quick limit만 변경되어야 한다.

### 필수 테스트 3 — Determinism
동일 데이터 / 동일 설정으로 두 번 실행했을 때 JSON 핵심 결과가 동일해야 한다.

### 필수 테스트 4 — Look-ahead 방지
평가일 이후 데이터가 candidate 생성에 들어가면 테스트 실패.

### 필수 테스트 5 — 탈락 단계 추적
의도적으로 제한 밖 종목을 넣은 fixture에서 정확한 drop stage가 기록되어야 한다.

---

## 12. 완료 조건

아래를 모두 만족해야 완료다.

- [ ] Production Scanner 결과 변경 없음
- [ ] Baseline / A / B / C를 동일 데이터로 실행 가능
- [ ] 종목별 pruning stage 추적 가능
- [ ] Candidate recall loss 계산 가능
- [ ] Top5 5/10/20D 성과 비교 가능
- [ ] T1/Stop/R 평가 가능
- [ ] 실행시간 기록 가능
- [ ] Look-ahead leakage 테스트 통과
- [ ] 결정론 테스트 통과
- [ ] 결과 JSON/CSV/MD 생성
- [ ] 어떤 제한이 병목인지 결론 또는 INCONCLUSIVE로 판정 가능

---

## 13. 이번 작업에서 하지 않는 것

- Production의 160/18 기본값 변경
- Strategy Top 3 문제 수정
- MA120 입력 문제 수정
- 중복 Strategy condition 수정
- Ranking 공식 변경
- ATR 기반 Ranking 적용
- Market Regime 변경
- Historical Evidence를 Ranking에 재투입
- ML 모델 도입
- Scanner 실행속도 최적화

이 항목들은 이번 결과를 본 뒤 하나씩 별도 작업으로 진행한다.

---

## 14. 다음 작업 연결

이번 감사가 끝나면 결과에 따라 다음 작업을 결정한다.

1. 초기 pruning이 실제 병목이면:
   - `B.2.3.4c.2 — Candidate Pool Policy Improvement`

2. 초기 pruning 영향이 작으면:
   - `B.2.3.4c.2 — Strategy Search Top3 vs All Audit`

즉 다음 단계도 결과 없이 미리 Production 수정하지 않는다.
