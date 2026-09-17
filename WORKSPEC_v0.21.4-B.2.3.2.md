# WORKSPEC v0.21.4-B.2.3.2 — Entry / Stop Price Plan Consistency Audit

## 목적
Scanner의 전략 기반 관심/진입 가격과 Risk Engine의 진입 기준·손절 참고구간·전략 무효화 기준·목표가격을 함께 표시할 때 가격 관계가 모순되거나 사용자에게 같은 개념처럼 보이는 문제를 진단하고 설명한다.

## 실제 코드 추적 결과
1. Scanner의 `price_rule`은 Strategy 조건을 사람이 이해할 수 있는 가격 기준으로 환산한다.
2. Risk Engine의 `entry_price`, `stop_zone_*`, `invalidation_price`, `target*`는 별도 Risk plan에서 생성된다.
3. 따라서 Strategy 관심구간과 Risk stop은 독립적으로 생성되며, UI에서 합쳤을 때 overlap이 생길 수 있다.
4. 실제 UI mapping 불일치도 확인했다.
   - Scanner 후보 비교 행: `stop_zone_low ~ stop_zone_high`를 `손절 참고`로 표시.
   - 기존 선택 상세 `EntryRiskGuideCard`: `invalidation_price`를 `손절 참고`로 표시.
   - 즉 서로 다른 두 값을 같은 이름으로 노출하고 있었다.
5. 기존 상세 Risk 화면(App.tsx)은 이미 `전략 무효화 기준`과 `손절 참고구간`을 별도 필드로 구분하고 있었다.

## 수정 원칙
- Entry/Stop/Invalidation/Target 숫자를 overlap 해소 목적으로 임의 변경하지 않는다.
- Strategy score 및 Scanner Ranking을 변경하지 않는다.
- KRX/Market Store/분석 기준일/Backtest/Production Exit Policy를 변경하지 않는다.
- 가격 관계 진단은 표시·진단 계층이며 기존 계산의 입력으로 사용하지 않는다.

## Backend 변경
### `backend/app/backtest/entry_risk_guide.py`
`price_consistency` 진단을 `ConcreteEntryRiskGuide`에 추가했다.

검사 항목:
- 0 이하 가격
- 진입 구간 상·하단 역전
- 손절 구간 상·하단 역전
- Risk 진입 기준 대비 invalidation/stop 위치
- Target1이 Risk 진입 기준 이하인지
- Target2가 Target1보다 낮은지
- RANGE 진입 구간과 stop zone 실제 overlap
- RANGE 진입 구간과 invalidation overlap
- raw 값은 분리돼 있지만 KRX 표시 단위 반올림 후 같거나 겹쳐 보이는 상태

상태:
- `OK`
- `WARNING`
- `INVALID`
- `NOT_APPLICABLE`

주요 진단 코드:
- `ENTRY_STOP_OVERLAP`
- `STOP_ZONE_ABOVE_ENTRY_RANGE`
- `ENTRY_INVALIDATION_OVERLAP`
- `INVALIDATION_ABOVE_ENTRY_RANGE`
- `TARGET1_AT_OR_BELOW_RISK_ENTRY`
- `TARGET2_BELOW_TARGET1`
- `ENTRY_RANGE_REVERSED`
- `STOP_ZONE_REVERSED`
- `DISPLAY_ROUNDING_TOUCH`

진단은 기존 가격을 재작성하지 않는다.

## 사용자 UI 변경
### Scanner 후보 비교/선택 상세
- `손절 참고`는 실제 `stop_zone_low ~ stop_zone_high`를 사용한다.
- KRX 표시용 stop zone 값이 있으면 표시값을 사용한다.
- `전략 무효화 기준`은 별도 정보로 표시한다.
- 두 개념이 같지 않음을 명시한다.

### 가격 관계 설명
정상 관계에서는 예를 들어:
`손절 참고 상단은 진입 검토 구간 하단보다 1,000원 (2.00%) 아래입니다.`

실제 overlap이면:
`가격 계획을 다시 확인해야 합니다. 현재 진입 검토 구간과 손절 참고가격이 겹쳐 해석이 명확하지 않습니다.`

표시 반올림만의 문제이면 raw 계산 충돌과 구분해 안내한다.

내부 진단 코드 이름을 사용자 화면에 직접 노출하지 않는다.

## 10개 전략 감사
다음 10개 전략의 기존 가격 조건 변환이 유지되는지 테스트했다.
1. Trend Following
2. Pullback
3. Breakout
4. Support Bounce
5. Oversold Bounce
6. Range Trading
7. Momentum Continuation
8. Volatility Squeeze
9. MA20 Rebound
10. Trend Recovery

Breakout처럼 현재가가 trigger 아래에 있는 것이 정상일 수 있는 전략은 그 사실만으로 오류 처리하지 않는다.

## 테스트 결과
### 실제 실행
- `test_entry_risk_guide_v0211.py`
- `test_price_plan_consistency_v0214b232.py`
- `test_candidate_priority_v0213.py`
- 합계 54 tests PASS

새 테스트에는 다음 케이스가 포함된다.
- 정상 Entry/Stop
- Stop == Entry low
- Stop이 Entry 내부
- Stop이 Entry 위
- Invalidation이 Entry 내부
- Target1 역전
- Target2 역전
- Entry/Stop range 역전
- raw는 정상이나 표시 반올림 후 접촉
- Breakout current < trigger 정상 처리
- overlap 진단이 action/Risk 가격을 변경하지 않는지
- 10개 전략 가격 규칙 유지

### Frontend
- B.2.3 Compact Workspace 회귀 PASS
- B.2.3.1 selected candidate session 회귀 PASS
- B.2.2.2 Typography/Readability 회귀 PASS
- B.2.2.1 Dark Theme 회귀 PASS
- B.2.2.2a Strategy Detail layout 회귀 PASS
- B.2.2.2b Scanner session/date consistency 회귀 PASS
- B.2.3.2 가격 mapping 정적 회귀 PASS
- 변경 TSX/API TypeScript syntax transpile PASS

### Full pytest 제한
현재 검증 환경은 전체 프로젝트가 아니라 overlay 조립본이다. 전체 pytest 수집을 시도했으나 기반 프로젝트의 `app.backtest.audit`, `app.backtest.history_store`가 overlay 세트에 없어 일부 기존 테스트가 import 단계에서 중단됐다. 따라서 Full pytest PASS라고 보고하지 않는다.

### 실제 사용자 데이터 제한
이 환경은 사용자 PC의 현재 KRX/Market Store를 직접 실행하지 않았으므로 실제 운영 후보 중 overlap 건수가 몇 건인지는 확정하지 않는다. 새 진단은 사용자 PC의 다음 Scanner 실행에서 각 후보의 `price_consistency`로 실제 상태를 확인할 수 있다.

### 실제 브라우저
이번 환경에서 실제 사용자 PC 브라우저 UI를 실행한 것은 아니다. B.2.3.1 실제 화면은 사용자가 정상이라고 확인한 상태에서 해당 구조를 유지했다.

## 변경하지 않은 것
- KRX 데이터 파이프라인
- B.2.2.2d 무결성 로직
- Strategy 계산 공식
- Strategy score
- Scanner Ranking
- Risk 가격 생성 공식
- Entry/Stop/Invalidation/Target 원값
- Historical Evidence 계산
- Backtest
- Production Exit Policy
- Profit Protection

## 버전 정의
`v0.21.4-B.2.3.2`는 가격을 새로 최적화하는 버전이 아니라, 서로 다른 Strategy 가격 기준과 Risk 가격 기준을 같은 화면에서 안전하게 비교하고, `손절 참고구간`과 `전략 무효화 기준`을 명확히 분리하며, 실제 충돌을 자동 진단하는 버전이다.
