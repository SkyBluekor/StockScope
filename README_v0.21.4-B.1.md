# StockScope v0.21.4-B.1 — Exit Policy Selection & Validation

연구용 Exit Policy 선택/검증 단계입니다. Production Scanner/Action Plan 청산 정책은 변경하지 않습니다.

## 핵심
- 여러 종목의 동일 기간 Exit Policy Audit을 하나의 보고서로 집계
- 가중치 점수 없음: Net Return / Profit Factor / MDD의 Pareto 비교
- 표본 부족 → `INSUFFICIENT_SAMPLE` + 기존 `TARGET1_FULL_EXIT` fallback
- 기존 정책 우위 → `BASELINE_BETTER`
- 수익/위험 trade-off 또는 단일 종목 편중 → `UNRESOLVED`
- 유일한 비열위 정책 + 표본/편중 guardrail 통과 → `SELECTED`
- Target2 이후 `Trailing horizon` vs `Hard Max Hold`도 별도 검증
- 시장상태별 집계 및 Profit Giveback 집계
- 결과는 `backend/runtime/research/exit_policy_selection.json`에 저장
- `production_policy_changed = false` 고정

## Research API
- `POST /api/backtest/exit-policy-selection`
- `POST /api/backtest/exit-policy-selection/jobs`

예시 요청:
```json
{
  "stocks": [
    {"code": "005930", "market": "KOSPI"},
    {"code": "000660", "market": "KOSPI"},
    {"code": "035420", "market": "KOSPI"},
    {"code": "247540", "market": "KOSDAQ"}
  ],
  "start_date": "2023-09-15",
  "end_date": "2026-09-15",
  "max_holding_days": 20,
  "round_trip_cost_pct": 0.0,
  "minimum_stock_count": 3,
  "minimum_total_trades": 30,
  "post_target2_research_days": 60
}
```

`minimum_stock_count=3`, `minimum_total_trades=30`은 통계적 유의성을 주장하는 값이 아니라, 기존 연구 최소표본 10건을 여러 종목에 걸쳐 확인하기 위한 투명한 연구 guardrail이며 요청 시 조정할 수 있습니다.

## 이번 버전에서 하지 않는 것
- Profit Protection Production 적용
- Scanner/Action Plan UI 변경
- 부분 익절
- 자동 주문
- Strategy/Ranking/Risk 공식 변경

실제 Production 연결은 v0.21.4-B.2에서 별도 승인 후 진행합니다.
