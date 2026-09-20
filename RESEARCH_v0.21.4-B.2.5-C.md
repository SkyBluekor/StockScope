# B.2.5-C Ranking Tie-break Research

## 결론

Production Ranking의 기존 우선순위 모델은 유지한다.

완전히 동일한 base priority key를 가진 후보 그룹에서만 다음 규칙을 추가한다.

```text
기존 우선순위 완전 동률
→ 기존 RiskPlan에 이미 존재하는 structural_target1_price 확인
→ 구조 목표까지의 거리가 가장 가까운 후보 1개만 그룹 맨 앞으로 승격
→ 나머지 후보는 기존 종목코드 순서를 그대로 유지
```

정책명: `STRUCTURAL_TARGET_NEAREST_PROMOTE`

Historical Evidence, 미래 outcome, 1.5R cap 값은 현재 Ranking 입력으로 사용하지 않는다.

## 왜 전체 재정렬이 아닌가

동률 후보 전체를 Risk/Target 거리로 정렬하는 방식은 표본에 따라 Top3/Top5 결과가 흔들렸다.
반면 **가장 가까운 구조 목표 후보 1개만 승격**하면 변경 폭이 작고 두 독립 감사 표본에서 Top1 및 상위 후보 지표가 더 안정적이었다.

## 표본 A — 80 evaluation dates

소스: `scanner-strategy-audit_20260918-104625.json`
Scanner version: `0.21.3.3`

현재 `final_sort_key`에서 종목코드를 제외한 나머지 key가 완전히 같은 그룹만 대상으로 재배치했다.
80일 중 74일에서 Top5 내 exact tie가 존재했다.

### Top1

| Horizon | Current Target-first | Promote Target-first | Current Stop-first | Promote Stop-first | Current Avg Return | Promote Avg Return |
|---|---:|---:|---:|---:|---:|---:|
| 5D | 31.25% | 40.00% | 51.25% | 47.50% | 0.536% | 0.671% |
| 10D | 36.25% | 43.75% | 53.75% | 51.25% | 1.387% | 1.425% |
| 20D | 41.25% | 47.50% | 56.25% | 51.25% | 2.986% | 2.869% |

20D 평균 수익률은 0.117%p 낮았지만 Target-first는 +6.25%p, Stop-first는 -5.00%p였다.
StockScope의 목적이 최대 수익률 고정이 아니라 더 좋은 판단이 나올 가능성을 높이는 것이라는 점에서 후보 비교 근거로 검토 가치가 있었다.

### Top3

| Horizon | Current Target-first | Promote Target-first | Current Avg Return | Promote Avg Return |
|---|---:|---:|---:|---:|
| 5D | 22.81% | 28.51% | -0.160% | 0.027% |
| 10D | 30.70% | 34.21% | 0.001% | 0.560% |
| 20D | 34.21% | 37.72% | 0.840% | 1.499% |

## 표본 B — Target1 realism 20-date smoke

소스: `target1-realism-audit_20260919-192434.json`
Scanner version: `0.21.3.5`

20 evaluation dates 중 실제 signal이 존재한 날짜는 18일이었다.
이 파일에는 full `final_sort_key`가 없으므로 exact-tie 재현이 아니라 READY/ENTRY_CANDIDATE 연속 그룹에서 **1개만 승격하는 보수적 proxy**로 확인했다.
Outcome 평가는 Production으로 채택된 `CAP_1_5R` 기준을 사용했다.

### Top1

| Horizon | Current Target-first | Promote Target-first | Current Stop-first | Promote Stop-first | Current MFE | Promote MFE | Current MAE | Promote MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 5D | 38.89% | 50.00% | 50.00% | 38.89% | 8.363% | 13.367% | -4.309% | -3.692% |
| 10D | 44.44% | 55.56% | 50.00% | 44.44% | 11.033% | 15.229% | -5.639% | -5.318% |
| 20D | 50.00% | 55.56% | 50.00% | 44.44% | 16.383% | 23.041% | -8.423% | -6.331% |

이 표본은 exact tie key를 보존하지 않으므로 보조 근거이며 Production 검증의 단독 근거로 사용하지 않는다.

## 현재 2026-09-18 Top5에 적용한 결과

기존 Top5는 base Ranking component가 모두 동일해서 종목코드로 순서가 결정됐다.

구조 목표 거리:

```text
삼성화재       7.0988%
한화           5.6604%
POSCO홀딩스    3.8700%
DB손해보험    11.2895%
한미사이언스  25.7732%
```

새 규칙은 그룹 전체를 거리순으로 재정렬하지 않는다.
가장 가까운 POSCO홀딩스만 앞으로 승격하고 나머지는 기존 코드 순서를 유지한다.

```text
Before
1 삼성화재
2 한화
3 POSCO홀딩스
4 DB손해보험
5 한미사이언스

After
1 POSCO홀딩스   <- structural focus
2 삼성화재
3 한화
4 DB손해보험
5 한미사이언스
```

## 안전선

- exact base priority tie에서만 동작
- READY가 WATCH를 넘지 않음
- missing/risk/entry gap/strategy fit 차이를 절대 덮어쓰지 않음
- Structural Target이 없으면 기존 code stable order 유지
- Historical Evidence를 Ranking에 사용하지 않음
- 미래 outcome을 Production 계산에 사용하지 않음
- Target1 1.5R cap 정책 변경 없음
- Entry / Stop / Target2 / Strategy 조건 변경 없음

## 버전

Production Ranking 의미가 바뀌므로 Scanner decision version을 `0.21.3.6` → `0.21.3.7`로 올린다.
같은 날 기존 backend cache와 섞이지 않도록 하기 위한 변경이다.
