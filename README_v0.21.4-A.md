# StockScope v0.21.4-A — Exit Policy Research & Backtest Audit

## 추가된 것

- `backend/app/backtest/exit_policy_research.py`
  - 기존 Target1 전량 종료와 Profit Protection 후보 비교
  - ATR 1.5 / 2.0 / 2.5 grid
  - MA20 Trail
  - Confirmed Swing Low Trail
  - Target2 이후에만 Profit Protection 활성화
  - 보호선 non-decreasing
  - previous protection 우선 판정으로 same-candle look-ahead 방지
  - Profit Giveback 지표 추가
- `backend/app/backtest/service.py`
  - Research-only `run_exit_policy_audit()` 추가
- `backend/app/api/backtest.py`
  - `/api/backtest/exit-policy-audit`
  - `/api/backtest/exit-policy-audit/jobs`
- `backend/tests/test_exit_policy_research_v0214a.py`
- `docs/exit-policy-research-v0.21.4-A.md`

## 중요한 비변경 사항

- 현재 Scanner Ranking 변경 없음
- 현재 Action Plan Exit 문구 변경 없음
- Historical Evidence의 기존 Target1 정책 변경 없음
- Strategy / Risk threshold 변경 없음
- 실제 매도/주문 기능 없음
- v0.21.4-A 결과만으로 Exit 정책 자동 확정하지 않음

## 검증

- v0.21.4-A 핵심 단위 테스트: 11/11 통과
- v0.21.3 Candidate Ranking + v0.21.2 Historical Evidence + v0.21.1 Entry/Risk + Multi Strategy 포함 관련 누적 회귀: 84/84 통과
- 변경 Python 파일 `py_compile` 통과

전체 backend test suite는 overlay 조립 테스트 환경의 오래된 fixture/version 혼합 때문에 별도 legacy 테스트들이 현재 코드 모델과 충돌하므로 통과했다고 주장하지 않는다. 이번 변경과 직접 연관된 누적 회귀 묶음은 위와 같이 통과했다.
