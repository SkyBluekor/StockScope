# WORKSPEC v0.21.4-B.2.3.4c.2
## Temporal Spread Validation for Quick Pool 18 vs 36

### 0. 실행 설정
- 모델: GPT-5.6 Sol
- 권장 추론 수준: Medium
- 목표: B.2.3.4c.1에서 발견된 `Quick 18 → 36` 개선 신호가 특정 짧은 기간의 우연인지 검증
- 원칙: Production Scanner 기본값 변경 금지, 감사/검증 코드만 수정
- High로 상향하는 조건: 평가일 샘플링이 데이터 누락/거래일 캘린더 문제로 복잡해질 때만

---

## 1. 배경

B.2.3.4c.1의 20거래일 감사 결과:

- BASELINE `160/18`: Top5 20D 평균수익률 6.090464%, 평균 R 0.326421
- QUICK_EXPANDED `160/36`: Top5 20D 평균수익률 6.148322%, 평균 R 0.365721
- MARKET_EXPANDED `320/18`: BASELINE보다 전반적으로 열위
- BOTH_EXPANDED `320/36`: BASELINE보다 전반적으로 열위

하지만 20개 평가일이 2026-07-16 ~ 2026-08-13에 몰려 있었고,
Quick 36과 Baseline의 Top5가 실제로 달라진 날은 매우 적었다.

따라서 현재 결과만으로 Production의 quick pool을 18에서 36으로 변경하면 안 된다.

이번 작업은 다음 질문만 검증한다.

> **Quick pool 36의 개선 효과가 넓은 기간과 서로 떨어진 평가일에서도 반복되는가?**

---

## 2. 핵심 가설

### H0
`18 → 36`에서 보인 개선은 특정 짧은 기간 또는 소수 날짜의 우연이며,
기간을 넓히면 성능 차이는 사라진다.

### H1
`18 → 36`은 서로 다른 시장 환경과 시기에서도
Top5 품질을 반복적으로 개선한다.

---

## 3. 이번 실험에서 비교할 Variant

이번에는 변수 수를 줄인다.

### BASELINE
- Market limit: 160
- Quick limit: 18

### QUICK_EXPANDED
- Market limit: 160
- Quick limit: 36

`320/18`, `320/36`은 이번 실험에서 제외한다.

이유:
- 1차 감사에서 시장별 160→320 확대는 일관된 개선 신호가 없었음
- 이번 단계의 목적은 `18 vs 36`만 독립적으로 재검증하는 것

---

## 4. 평가일 샘플링 정책

연속된 최근 20거래일이 아니라,
가능한 전체 로컬 데이터 기간에 평가일을 넓게 분산한다.

### Stage A — Main Validation
목표:
- 최소 60개 평가일
- 권장 80개 평가일
- 데이터 기간 전체에 가능한 균등 분산

샘플링 원칙:
1. 미래 20거래일 성과를 계산할 수 있는 날짜만 선택
2. 날짜를 단순 최근순으로 80개 고르지 않음
3. 전체 유효 기간을 동일 간격으로 분산
4. 동일 주/인접 거래일 과도한 중복 방지
5. 가능하면 최소 3~5거래일 간격 유지

### Stage B — Optional Weekly Validation
Stage A 결과가 애매할 경우:
- 전체 유효 기간에서 주 1회 수준으로 평가
- 평가일 수를 늘려 결과 방향 재확인

---

## 5. 데이터 독립성 / 누수 방지

각 평가일 `t`에 대해:

- Scanner 입력: `t`일까지의 데이터만 사용
- 미래 성과 측정: `t+1` 이후 데이터만 사용
- 5D / 10D / 20D outcome은 평가용으로만 사용
- 미래 데이터가 quick score, strategy, rank, price plan에 들어가면 실패 처리

기존 leakage 테스트를 그대로 유지하고,
분산 샘플링에서도 동일하게 적용한다.

---

## 6. Primary 평가 항목

이번 실험의 Primary는 `Top5 품질`이다.

### A. Top5 20D
- 평균 forward return
- 중앙값 forward return
- 평균 R
- Target1-first 비율
- Stop-first 비율
- MFE
- MAE

### B. Top5 10D
동일 지표

### C. Top5 5D
동일 지표

---

## 7. 가장 중요한 추가 측정

### 7.1 Top5 Change Frequency
각 평가일에서:

- BASELINE Top5
- QUICK_EXPANDED Top5

가 실제로 얼마나 자주 달라지는지 측정한다.

기록:
- changed_dates
- unchanged_dates
- change_rate_pct
- 평균 교체 종목 수
- 최대 교체 종목 수

Quick 36이 대부분의 날짜에서 동일한 Top5를 만든다면,
성능 차이가 소수 outlier에 의해 생긴 것인지 반드시 따진다.

### 7.2 Paired Replacement Analysis
Top5가 달라진 날짜만 따로 모은다.

각 교체에 대해:
- 빠진 종목
- 새로 들어온 종목
- rank
- 5D / 10D / 20D return 차이
- R 차이
- T1/Stop 결과 차이

즉:
`새 종목 - 기존 종목`의 paired delta를 계산한다.

### 7.3 Date-level Delta
각 평가일별로:

- QUICK_EXPANDED Top5 평균 성과
- BASELINE Top5 평균 성과
- 차이

를 저장한다.

평균 하나만 보지 않고:
- 개선 날짜 수
- 악화 날짜 수
- 동일 날짜 수
- 중앙값 delta
- 하위 꼬리 delta

를 본다.

---

## 8. 결과 안정성 검사

평균 수익률 하나로 결론 내리지 않는다.

반드시 함께 확인:
- 평균
- 중앙값
- 날짜별 승/패 비율
- 극단값 제거 전/후 방향
- 5D / 10D / 20D 방향 일치 여부
- R 결과 방향
- T1/Stop 방향

### 간단한 Robustness
상위/하위 극단 날짜 각 5%를 제외한 trimmed 결과도 함께 계산한다.

이유:
소수 급등 종목이 전체 평균을 왜곡하는지 확인하기 위함.

---

## 9. 판정 규칙

### KEEP_18
다음 중 하나 이상이면 현재 18 유지:
- Quick 36 개선이 특정 날짜 몇 개에만 집중
- median delta가 0에 가깝거나 음수
- 5D/10D/20D 방향이 일관되지 않음
- 평균 R 개선이 반복되지 않음
- 계산비용 증가 대비 실질 개선이 작음

### CONSIDER_36
아래 조건을 대부분 만족할 때만:
- 여러 시기에 걸쳐 Top5 교체 발생
- 교체된 날짜의 paired delta가 반복적으로 양수
- 10D/20D 평균 및 중앙값이 모두 개선
- 평균 R도 개선
- Stop-first가 악화되지 않음
- 특정 1~2개 날짜를 제거해도 개선 방향 유지

### INCONCLUSIVE
- 변화 날짜 수 자체가 너무 적음
- 기간별 결과가 서로 반대
- 표본이 부족
- 데이터 누락으로 평가 범위가 지나치게 좁음

---

## 10. 성능 비용도 기록

Variant별:
- 총 runtime
- 날짜당 평균 runtime
- Quick 18 대비 Quick 36 추가 비용
- 최종 평가 대상 수

이번 단계는 품질 검증이 우선이지만,
Quick 36의 성능 향상이 미미한데 비용이 크게 늘면 Production 변경 근거가 약하다.

---

## 11. 구현 범위

기존 B.2.3.4c.1 감사 러너를 확장한다.

### 수정 대상 권장
- `backend/app/backtest/scanner_quality/early_pruning_audit.py`
- `backend/tools/run_scanner_pruning_audit.py`
- 관련 테스트

### 추가 기능
- 분산 날짜 샘플링
- Variant 선택 옵션
- paired replacement 분석
- date-level delta
- trimmed summary
- change frequency 통계

Production `scanner.py` 기본 동작은 변경하지 않는다.

---

## 12. CLI 권장

기본 실행:

```bash
python tools/run_scanner_pruning_audit.py --mode temporal-validation
```

권장 옵션:

```bash
python tools/run_scanner_pruning_audit.py \
  --mode temporal-validation \
  --sample-size 80 \
  --min-date-gap 3
```

정확한 옵션명은 현재 CLI 구조와 충돌하지 않게 구현 시 맞춘다.

---

## 13. 출력물

기존 출력 위치 유지:

`backend/runtime/quality_audit/pruning/`

### JSON
- 전체 설정
- 샘플링된 평가일
- Variant별 전체 결과
- date-level delta
- replacement pair
- change frequency
- trimmed 통계

### CSV
기존 signal CSV 외에 필요하면:

`scanner-pruning-pairs_<timestamp>.csv`

컬럼 예:
- analysis_date
- removed_ticker
- added_ticker
- baseline_rank
- expanded_rank
- return_5d_delta
- return_10d_delta
- return_20d_delta
- r_20d_delta
- baseline_event
- expanded_event

### Markdown Summary
최상단에 바로 표시:
- Valid dates
- Changed dates / Change rate
- 5D / 10D / 20D delta
- Mean / Median / Trimmed mean
- R delta
- 판정: KEEP_18 / CONSIDER_36 / INCONCLUSIVE

---

## 14. 필수 테스트

### Test 1 — Production 불변
감사 코드 변경 전/후 Production Scanner 결과 동일

### Test 2 — Sampling Determinism
같은 DB / sample-size / gap으로 실행하면 평가일 목록 동일

### Test 3 — Temporal Spread
샘플링 날짜가 최근 연속 구간에 몰리지 않는지 확인

### Test 4 — Variant Isolation
160은 고정되고 quick limit만 18/36으로 달라져야 함

### Test 5 — Paired Replacement
Top5 교체 fixture에서 빠진/들어온 종목과 delta가 정확히 계산

### Test 6 — No Look-ahead
미래 데이터가 Scanner 입력에 사용되면 실패

### Test 7 — Trimmed Metric
극단값 fixture에서 일반 평균과 trimmed 평균이 의도대로 분리

---

## 15. 완료 조건

- [ ] 최소 60개 이상 분산 평가일 실행 가능
- [ ] BASELINE 160/18 vs QUICK_EXPANDED 160/36만 비교 가능
- [ ] Top5 change rate 계산 가능
- [ ] 교체 종목 paired 분석 가능
- [ ] 날짜별 성과 delta 계산 가능
- [ ] 5D/10D/20D 평균/중앙값/R/T1/Stop 비교 가능
- [ ] trimmed 결과 계산 가능
- [ ] runtime 비교 가능
- [ ] deterministic sampling 테스트 통과
- [ ] look-ahead 테스트 통과
- [ ] Production Scanner 결과 변경 없음
- [ ] KEEP_18 / CONSIDER_36 / INCONCLUSIVE 중 하나로 판정 가능

---

## 16. 이번 작업에서 하지 않는 것

- Production quick limit 18→36 변경
- Market limit 160 변경
- Strategy Top3→All 수정
- MA120 입력 수정
- 중복 Strategy 조건 수정
- Ranking 공식 변경
- Market Regime 변경
- Historical Evidence 순위 재투입
- ML 도입

---

## 17. 다음 단계

이번 결과가:

### KEEP_18
quick pool 병목은 우선순위를 낮추고,
다음으로 `Strategy Top3 vs All Audit` 진행

### CONSIDER_36
Production 변경 전에 별도 `Quick Pool Policy Change` 명세 작성 후 적용

### INCONCLUSIVE
평가기간/표본을 한 번만 추가 확장하고 재검증

어떤 경우든 이번 작업에서 Production 정책은 바꾸지 않는다.
