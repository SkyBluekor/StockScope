# v0.21.3 Scanner Candidate Ranking & Priority Explanation

## 목적

Scanner 후보의 숫자 순위를 단순 내부 점수로 보여주지 않고, 사용자가 **왜 이 종목이 더 먼저 볼 후보인지** 이해할 수 있게 한다.

## 최종 우선순위 규칙

1. 현재 전략 조건
2. Risk
3. 기존 Concrete Entry & Risk Guide가 계산한 진입 기준까지의 실제 거리
4. 같은 전략의 최근 3년 Historical Evidence
5. 기존 Strategy Selector 적합도 (마지막 tie-breaker)

이 순서는 미래 상승확률이 아니다.

## Priority Tier

- READY: 현재 조건 충족 + Risk가 현재 진입 판단을 막지 않음
- NEAR_READY: 부족 조건 1~2개 + Risk가 현재 판단을 막지 않음
- WAIT: 현재 조건이 더 필요함
- RISK_HOLD: 현재 조건은 충족했지만 Risk 경고/차단
- LOW_PRIORITY: 조건 데이터 자체를 충분히 계산하지 못함

Historical Evidence는 Tier를 뒤집지 않는다. 즉 현재 조건이 부족한 종목이 과거 성과가 좋다는 이유만으로 READY 종목보다 위 Tier로 승격되지 않는다.

## Historical Evidence

- GOOD / FAIR: 동일 Tier 후보 비교의 보조 근거
- WEAK: 동일 Tier 안에서 불리한 근거
- INSUFFICIENT / NO_CASES / DATA_UNAVAILABLE: 현재 조건 실패로 바꾸지 않음

## 진입 근접도

새 임계값을 만들지 않는다. `entry_risk_guide.rebound_rule.gap_pct` 또는 `price_rule.gap_pct`가 실제로 있을 때만 사용한다. 값이 없으면 순위를 위해 임의의 가격 거리를 생성하지 않는다.

## 진단

응답 diagnostics의 `ranking_changes`에는 기존 preliminary 순위와 v0.21.3 최종 순위가 남는다. 사용자 기본 화면에는 raw score를 노출하지 않는다.
