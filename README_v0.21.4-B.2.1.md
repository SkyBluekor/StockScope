# StockScope v0.21.4-B.2.1 — Production Exit Policy Activation & Backtest Parity

v0.21.4-B.1/B.1.1에서 검증한 Exit 정책을 실제 백테스트에 안전하게 연결하는 Backend 단계입니다. Profit Protection 사용자 UI는 아직 추가하지 않습니다.

## 핵심 정책
- 연구 결과가 `SELECTED`인 전략만 검증된 trailing Exit 정책을 Production 후보로 활성화합니다.
- `BASELINE_BETTER / UNRESOLVED / INSUFFICIENT_SAMPLE`은 기존 `TARGET1_FULL_EXIT`를 유지합니다.
- 연구 리포트를 직접 실시간 참조하지 않고 `backend/runtime/research/exit_policy_production.json`에 Production mapping을 한 번 고정합니다.
- 이미 Production mapping이 있으면 이후 연구 재실행으로 자동 변경되지 않습니다.
- 명시적 force activation을 사용해야 최신 연구 결과로 mapping을 교체할 수 있습니다.
- 검증 리포트가 없거나 mapping이 손상되면 기존 `TARGET1_FULL_EXIT`로 안전하게 fallback합니다.

## 공통 Exit Engine
- Research와 Production이 같은 `ExitPolicySimulator`를 사용합니다.
- Target1은 trailing 정책에서 milestone입니다.
- Target2 도달 이후에만 Profit Protection을 활성화합니다.
- 보호선은 한 번 상승하면 내려가지 않습니다.
- 오늘 새 고점/지표로 보호선을 올리기 전에 전일까지 확정된 보호선 이탈 여부를 먼저 검사합니다.
- 선택된 정책에 필요한 Target2 구조를 만들 수 없는 개별 거래는 그 거래만 기존 Target1 Exit로 fallback합니다.

## Backtest parity
- 10전략 Multi Strategy Backtest가 Production mapping을 사용합니다.
- 기존 Pullback 단일 백테스트도 동일한 Production Exit Engine을 actual trade path에 사용합니다.
- 기존 연구용 entry-timing/risk-policy cohort는 기존 정책을 유지해 연구 정의가 섞이지 않게 합니다.
- Baseline 정책은 기존 `BacktestEngine._simulate_trade()` 결과를 그대로 사용합니다.

## Historical Evidence / Cache
- Historical Evidence에 실제 사용된 `exit_policy` / `historical_policy` metadata를 포함합니다.
- Scanner/Historical Evidence 캐시 키에 Production Exit Policy token을 포함합니다.
- Production mapping이 바뀌면 이전 Exit 정책의 Historical cache를 재사용하지 않습니다.

## API
- `GET /api/backtest/exit-policy-production/status`
- `POST /api/backtest/exit-policy-production/activate?force=false`

B.1.1 검증 리포트가 존재하고 Production mapping이 아직 없다면 B.2.1 사용 시 최초 1회 mapping을 고정합니다. 이후 연구 재실행은 기존 mapping을 자동 변경하지 않습니다.

## 이번 버전에서 하지 않는 것
- Action Plan Profit Protection UI
- Scanner Trailing UI
- 부분 익절
- Target3/Target4
- 실시간 주문/체결

## 검증
- Production Exit / Research / Selection / Validation Runner / Entry Risk / Candidate Ranking / Historical Evidence / Scanner / Single-stock Fast Path / Multi Strategy 관련 회귀 118개 통과
- 별도 Production baseline parity test로 기존 Target1 trade의 entry/exit/return 동일성 확인
- Python compile 통과
- 전체 프로젝트 full pytest 및 Vite production build는 실행했다고 주장하지 않습니다.
