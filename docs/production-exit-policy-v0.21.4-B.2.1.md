# Production Exit Policy — v0.21.4-B.2.1

## 흐름

1. B.1.1 `exit_policy_validation_report.json` 생성
2. `SELECTED`만 Profit Protection 정책으로 채택 가능
3. Production mapping `exit_policy_production.json`으로 고정
4. Multi Strategy / Pullback actual backtest가 동일한 Production Exit Engine 사용
5. Historical Evidence cache는 Production policy token별로 분리

## 안전한 fallback

- 검증 리포트 없음 → `TARGET1_FULL_EXIT`
- Strategy가 mapping에 없음 → `TARGET1_FULL_EXIT`
- 알 수 없는 policy id → `TARGET1_FULL_EXIT`
- Selected trailing이 개별 거래에서 Target2를 계산할 수 없음 → 해당 거래만 exact Target1 baseline

## Look-ahead 방지

Target2 이후 각 일봉에서 기존 보호선 이탈을 먼저 판단한 뒤, 거래가 유지된 경우에만 해당 일봉으로 다음 보호선을 계산합니다.

## Production mapping freeze

연구 결과 파일과 실제 정책 파일은 분리합니다. 한번 고정된 mapping은 이후 연구 재실행으로 자동 변경되지 않으며 명시적 force activation에서만 교체됩니다.
