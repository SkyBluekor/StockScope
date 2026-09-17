# WORKSPEC v0.21.4-B.2.3.3 — Decision Consistency & Theme Regression Stabilization

## 완료 목적
1. Light/Dark 토글이 상태 문자열만 바뀌고 실제 색상은 바뀌지 않던 회귀를 복구한다.
2. Scanner의 현재 판단과 10전략 과거검증의 현재 행동이 서로 다른 전략을 기준으로 충돌하는 문제를 해결한다.

## 실제 원인
- Theme: B.2.2.1에서 :root를 dark token으로 고정하면서 light token set이 사라졌다. App의 data-theme/localStorage 토글 자체는 정상이다.
- Decision: Scanner와 Backtest는 같은 current_readiness()를 사용하지만, Backtest select_strategy()가 historical 55% + current 45% blended rank 1위를 다시 대표 전략으로 선택하고 그 전략의 WAIT/READY를 종목 전체 현재 행동으로 사용했다.

## 구현
- :root를 Light canonical token으로 복원하고 html[data-theme="dark"]에서 동일 canonical token을 Dark 값으로 override한다.
- Scanner에서 상세분석 이동 시 code/market/data_date/strategy/action/checks/risk를 sessionStorage에 30분 TTL context로 저장한다.
- Backtest가 동일 종목 context를 읽어 Scanner 출처 판단과 기준일 일치 여부를 표시한다.
- select_strategy()는 현재 행동에 CURRENT_STATE_FIRST 규칙을 사용한다.
  - READY > WATCH > NOT_READY > CAUTION > BLOCKED
  - 동일 상태 안에서 risk 안전/조건완료/current score를 우선하고 historical은 후순위 tie-breaker로 사용한다.
- 기존 55/45 blended ordering은 과거/비교 순위로 유지하고 현재 행동을 결정하지 않는다.
- historical_best_strategy와 현재 대표 전략을 API에서 분리한다.
- READY인데 historical INSUFFICIENT/WEAK인 경우 현재 ENTRY_CANDIDATE를 WAIT로 뒤집지 않고 과거 근거를 별도 warning으로 표시한다.
- Backtest 결과 UI에서 `현재 조건 우선 전략`과 `과거 비교 1위`가 다르면 별도 영역으로 동시에 보여준다.

## 비변경
- Scanner Ranking 공식
- Strategy 계산
- Entry/Stop/Invalidation/Target1/Target2 공식
- Target1 Realism Audit
- Historical backtest execution policy
- Production Exit Policy

## 테스트
- READY Support Bounce + historical 강한 WAIT Pullback -> Current = Support Bounce ENTRY_CANDIDATE
- historical WEAK가 READY를 WAIT로 뒤집지 않음
- READY가 없으면 현재 조건이 더 가까운 WAIT 선택
- Risk BLOCKED는 ENTRY_CANDIDATE가 되지 않음
- Target1 audit 기존 테스트 포함 선택 Backend 10 tests PASS
- Light/Dark token, toggle wiring, Scanner context, Current/Historical split 정적 회귀 PASS
- 변경 TS/TSX syntax PASS

## 한계
- 이 실행 환경에서는 실제 사용자 브라우저/Vite 앱을 띄워 Light/Dark 화면을 픽셀 단위로 검증하지 않았다.
- 조립용 overlay 세트는 원 프로젝트 전체가 아니므로 full pytest/Vite production build 완료를 주장하지 않는다.
