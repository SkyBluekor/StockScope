# Exit Policy Selection & Validation — v0.21.4-B.1

## 선택 원칙
StockScope는 정책별 임의 가중치 점수를 생성하지 않는다. 정책 선택은 충분표본 후보에 대해 평균 Net Return, Profit Factor, 종목별 일일종가 MTM MDD 중앙값을 동시에 비교한다.

한 후보가 기존 Target1 종료보다 모든 비교 가능한 핵심 지표에서 열위가 없고 최소 한 지표가 개선돼야 baseline 개선 후보가 된다. 개선 후보가 여러 개이면서 서로 trade-off가 있으면 `UNRESOLVED`로 남긴다.

## 종목 편중 방지
새 정책의 양(+) 개선 기여 중 한 종목의 기여가 나머지 모든 양(+) 기여 합보다 크면 `single_stock_dominant=true`로 판정하고 자동 선택하지 않는다.

## 정확한 집계
v0.21.4-A 연구 엔진에 거래 합산용 primitive를 추가한다.
- trades / wins
- net return sum
- positive net return sum
- negative net return absolute sum
- holding-days sum
- profit-giveback sum

따라서 여러 종목 Profit Factor를 단순 평균하지 않고 전체 이익합 / 전체 손실절대합으로 다시 계산한다.

## Max Hold 연구
Profit Protection 후보는 두 가지를 비교할 수 있다.
1. `TRAILING_HORIZON_AFTER_TARGET2`: Target2 이후 기존 20일 제한보다 trailing 연구 horizon 우선
2. `HARD_MAX_HOLD`: Target2 이후에도 기존 max holding 강제

둘 중 하나가 Pareto 우위를 보이지 않으면 이 역시 `UNRESOLVED`다.

## Look-ahead 정책
기존 v0.21.4-A 규칙을 유지한다. 오늘 종가가 전일까지 확정된 보호선을 지켰을 때만 오늘 데이터로 다음 거래일 보호선을 높인다.

## Production 안전장치
선택 보고서는 연구 결과일 뿐이며 `production_policy_changed=false`다. Scanner/Action Plan/Historical Evidence의 실제 Exit 정책은 v0.21.4-B.2 전까지 바뀌지 않는다.
