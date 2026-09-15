# StockScope v0.21.4-A — Exit Policy Research & Backtest Audit

## 목적

이 버전은 실제 Scanner/Action Plan의 청산 정책을 바꾸지 않는다. 기존 `Target1 전량 청산`을 기준선으로 두고, Target2 이후 수익을 보호하는 여러 Exit 후보를 같은 StockScope 전략 신호와 KRX EOD 데이터 경계에서 비교하기 위한 연구 계층이다.

## 비교 정책

1. `TARGET1_FULL_EXIT` — 현재 기준선. Target1 도달 시 전량 종료.
2. `ATR_TRAIL_1_5` — Target2 이후 Highest Close - ATR14 × 1.5.
3. `ATR_TRAIL_2_0` — Target2 이후 Highest Close - ATR14 × 2.0.
4. `ATR_TRAIL_2_5` — Target2 이후 Highest Close - ATR14 × 2.5.
5. `MA20_TRAIL` — Target2 이후 MA20을 보호 후보로 사용.
6. `CONFIRMED_SWING_LOW_TRAIL` — 좌우 2개 봉으로 확정된 최근 Swing Low를 보호 후보로 사용.

ATR 배수는 이번 단계에서 하나를 정답으로 고정하지 않는다.

## 공통 실행 정책

- 진입: 기존 StrategyEngine 신호가 새로 시작된 뒤 다음 거래일 시가.
- 초기 손절: 기존 RiskEngine invalidation price.
- 같은 일봉에서 초기 손절과 Target2가 모두 닿으면 `STOP_FIRST_CONSERVATIVE`.
- Target1: Profit Protection 후보에서는 milestone.
- Target2: Profit Protection 활성화 milestone.
- Target2 이전: 기존 max holding day를 유지.
- Target2 이후: 연구용으로 최대 60거래일까지 추가 추적. Production 정책이 아니다.
- Trailing Exit: 확정 종가가 기존 보호선 아래로 내려간 경우.
- 보호선 갱신: 오늘 종가 판단이 끝난 뒤 오늘 데이터를 이용해 내일 보호선을 계산.
- 보호선은 절대 하락하지 않는다.
- 기존 hard stop은 trailing 이후에도 유지한다.

## Look-ahead 방지

오늘 고점 또는 오늘 종가로 계산된 새 보호선은 오늘의 Exit 판단을 취소할 수 없다. 오늘은 전일까지 확정되어 있던 보호선으로 먼저 판단하고, 살아남은 경우에만 오늘 데이터를 반영해 다음 거래일 보호선을 올린다.

Swing Low 역시 오른쪽 2개 봉까지 이미 종료된 pivot만 사용한다.

## 평가 지표

기존 Backtest 지표:

- Trades / Win Rate
- Average Net Return
- Profit Factor
- Daily-close Mark-to-market MDD
- Average Holding Days

v0.21.4-A 추가 지표:

- Average Peak Return
- Average Profit Giveback (percentage points)
- Median Profit Giveback
- Peak profit 대비 평균 Giveback 비율
- Target1 도달 거래 수
- Target2 도달 거래 수
- Trailing Exit 거래 수
- Target2 전 Time Exit 수
- Research Horizon Exit 수

`profit_giveback_pct_points` 예시:

- 진입 100
- 보유 중 최고 종가 130 (+30%)
- Exit 115 (+15%)
- Giveback = 15%p

## 정책 자동 확정 금지

`metric_leaders`는 각 지표에서 수치상 선두인 정책만 표시한다. 하나의 합산 점수나 임의 가중치로 Production 정책을 자동 선정하지 않는다.

최종 v0.21.4-B 정책은 전략별 실제 표본을 보고 Net Return / PF / MDD / Giveback / 보유기간을 함께 검토한 뒤 결정한다.

표본이 10건 미만이면 `sample_sufficient=false`로 표시한다.

## API

기존 앱 흐름을 바꾸지 않는 연구용 endpoint를 추가한다.

- `POST /api/backtest/exit-policy-audit`
- `POST /api/backtest/exit-policy-audit/jobs`
- 기존 `GET /api/backtest/jobs/{job_id}`로 background job 결과 확인 가능.

기존 `PullbackBacktestRequest`와 같은 입력을 사용한다.

```json
{
  "code": "005930",
  "market": "KOSPI",
  "start_date": "2023-09-15",
  "end_date": "2026-09-15",
  "initial_capital": 10000000,
  "max_holding_days": 20,
  "round_trip_cost_pct": 0.0
}
```

이 API 결과는 Research-only이며 Scanner ranking, Historical Evidence, Action Plan 또는 실제 청산 판단을 변경하지 않는다.
