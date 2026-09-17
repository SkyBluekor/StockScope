# WORKSPEC v0.21.4-B.2.3.2a — Entry / Stop Overlap Root Cause Validation

## 목적
실제 Scanner 화면에서 `관심 가격`과 `손절 참고`가 겹쳐 보인 사례의 원인을 확정하고, 전략 조건 가격과 실행 리스크 가격을 같은 의미로 오해하지 않도록 교정한다. 가격·Ranking을 임의로 보정하지 않고 실제 생성 경로를 먼저 추적한다.

## 실제 확인 사례
사용자 화면에서 다음 5개 사례가 확인됐다.

| 종목 | 기존 관심 가격 | 손절 참고 | 겹침 |
|---|---:|---:|---:|
| 코스맥스 | 272,000~286,000 | 268,767~273,513 | 272,000~273,513 (1,513원, 조건밴드의 10.81%) |
| 비에이치아이 | 61,500~64,700 | 60,363~61,610 | 61,500~61,610 (110원, 3.44%) |
| 삼성SDI | 527,000~554,000 | 522,888~531,075 | 527,000~531,075 (4,075원, 15.09%) |
| 포스코인터내셔널 | 53,100~55,800 | 52,727~53,517 | 53,100~53,517 (417원, 15.44%) |
| 한국콜마 | 134,500~141,600 | 141,215~143,827 | 141,215~141,600 (385원, 5.42%) |

화면에서 확인된 5건 모두 `stop_zone_high < current_price` 관계는 만족했다. 다만 스크린샷에는 실제 `invalidation_price` 및 Backend raw payload가 모두 노출되지 않았으므로, 실제 사용자 PC의 해당 실행 전체 raw Risk payload를 이 환경에서 직접 재현했다고 주장하지 않는다.

## 원인 확정
### 1. 기존 `관심 가격`은 실행 가능한 Entry range가 아니었다
`entry_risk_guide._price_rule()`은 Strategy Engine의 조건 문자열을 가격으로 환산한다.

예:
- `현재가가 20일선과 X% 이내` → MA20 주변 조건 가격대
- `지지선과 X% 이내` → support 주변 조건 가격대
- `20일 고점과 X% 이내` → high20 주변 조건 가격대

또한 `_price_rule()`은 가격 관련 `FAIL` 조건을 먼저 찾는다. 따라서 조건이 부족한 후보에서는 "현재 조건을 만족하려면 어느 가격 조건이 필요한가"를 설명하는 가격대가 우선 표시될 수 있다.

즉 이 값은 **전략 조건/자격 판정 범위**이며 "이 범위 어디서든 매수 가능"이라는 뜻이 아니다.

### 2. Risk 가격은 별도 계산 계층이다
`entry_risk_guide._risk_payload()`은 Risk Plan의 다음 값을 그대로 전달한다.
- `entry_price` → 실행 리스크 기준가
- `invalidation_price`
- `stop_zone_low/high`
- `target1/target2`

전략 조건 가격대와 Risk Plan의 Entry/Stop은 서로 다른 계산 단계다. 따라서 두 범위가 수학적으로 겹친다는 사실만으로 실행 가격 계획 오류라고 판정할 수 없다.

### 3. 실제 오류 판정 기준
실제 실행 리스크 일관성은 다음 관계로 검사한다.
- `invalidation < risk_entry_reference`
- `stop_zone_high < risk_entry_reference`
- `target1 > risk_entry_reference`
- `target2 >= target1`
- 가격/범위 값은 양수이며 상·하단이 역전되지 않음

위 관계가 깨질 때만 `RISK_PLAN_INVALID`로 처리한다.

## Backend 변경
대상: `backend/app/backtest/entry_risk_guide.py`

### 전략 가격 의미 메타데이터
`price_rule`에 추가:
- `semantic_role`
- `user_label`
- `executable_entry_range`
- `semantic_note`

RANGE 기본 의미:
- `semantic_role = STRATEGY_CONDITION_BAND`
- `user_label = 전략 조건 가격대`
- `executable_entry_range = false`

### Price Consistency 재정의
기존 B.2.3.2에서 Strategy RANGE ↔ Stop overlap 자체를 충돌로 볼 수 있던 부분을 교정했다.

분류:
- `STRATEGY_CONDITION_BAND_OVERLAP`: 정보성. 계산 오류 아님.
- `DISPLAY_ROUNDING_TOUCH`: raw 값은 분리됐지만 표시 반올림 후 접촉/겹쳐 보임.
- `RISK_PLAN_INVALID`: Risk Entry / Stop / Invalidation / Target 관계 자체가 잘못됨.
- `SEPARATED`: 리스크 가격관계 정상.

`has_conflict`는 실제 `WARNING/INVALID`에서만 true다.

### overlap 계측
진단에 다음을 추가:
- overlap low/high
- overlap width
- condition range 대비 overlap ratio

### trace_context
기존 응답의 `price_consistency` 아래 개발 진단 정보를 추가한다.
- strategy
- analysis_date
- decision_reason
- current_price
- strategy_rule_status/basis/role
- risk_status/reference_only
- risk_entry_reference
- risk_structural_anchor/label

새 API endpoint는 추가하지 않았다.

## Frontend 변경
대상:
- `ScannerPanel.tsx`
- `EntryRiskGuideCard.tsx`
- `entryPricePosition.ts`
- `api.ts`
- `styles.css`

### 용어 교정
기존 오해 가능 표현:
- `관심 가격`
- `관심 구간`
- 모호한 `진입 참고`

변경:
- RANGE → `전략 조건 가격대`
- threshold → `전략 조건 기준가`
- `손절 참고` → `손절 참고구간`
- `핵심 가격 계획` → `핵심 가격 기준`

### 의미 설명
전략 조건 가격대에는 다음 취지의 설명을 제공한다.
> 전략 조건 충족 여부를 보기 위해 기준선을 가격대로 환산한 범위이며, 구간 전체가 매수 가능한 가격 범위를 뜻하지 않는다.

### 겹침 UI
전략 조건 가격대 ↔ Stop overlap은 경고(red warning)가 아니라 `가격 기준 구분` 문맥 정보로 표시한다.

실제 Risk 관계 오류만 `가격 계획 확인` warning/invalid로 표시한다.

### Invalidation
`전략 무효화 기준`은 `손절 참고구간`과 별개라는 기존 B.2.3.2 구분을 유지한다.

## 변경하지 않은 것
- Strategy 조건 계산
- Strategy score
- Scanner Ranking / candidate ordering
- Risk Engine 가격 공식
- Entry / Stop / Invalidation / Target raw 숫자
- KRX 데이터 파이프라인
- Market Store
- 분석 기준일
- Backtest
- Historical Evidence
- Production Exit Policy
- Profit Protection

## 실제 회귀 Fixture
5개 사용자 화면 사례를 Backend test fixture로 고정했다.

예상 결과:
- 5건 모두 `STRATEGY_CONDITION_BAND_OVERLAP`
- 상태 `OK`
- `has_conflict=false`
- overlap 수치 정확히 계산
- stop high가 Risk entry/current 기준 아래임을 fixture에서 확인

추가로 한국콜마와 유사한 `FAIL` 전략 조건 가격대가 현재가보다 아래에 있으면서 Stop과 겹치는 사례를 별도 회귀 테스트로 추가했다. 이 경우도 조건 가격대는 매수범위가 아니므로 자동 Risk 오류가 아니다.

## 검증 결과
### Backend targeted pytest
실행:
`PYTHONPATH=. pytest -q tests/test_price_plan_consistency_v0214b232.py tests/test_entry_stop_overlap_root_cause_v0214b232a.py tests/test_entry_risk_guide_v0211.py`

결과: **53 passed**

검증 포함:
- 10개 전략 가격 규칙
- 5개 실제 화면 fixture
- semantic overlap
- 실제 Risk stop >= Risk entry 오류
- Target 관계 오류
- display rounding touch
- FAIL 조건 가격대 우선 설명 사례
- trace_context

### Frontend 정적/런타임 단위 회귀
PASS:
- `pricePlanConsistency_v0214b232.py`
- `pricePlanRootCause_v0214b232a.py`
- `analysisDateConsistency_v0214b222b.ts`
- `scannerCompactRuntimeRegression_v0214b231.ts`
- `scannerCompactWorkspace_v0214b23.ts`
- `entryPricePosition_v0214a4.ts`
- `scannerSelectionSession_v0214b231.ts`
- `scannerSession_v0214b222b.ts`
- Dark Theme regression
- Readability regression
- Strategy layout regression
- 변경 TS/TSX syntax transpilation

### Full pytest
**PASS로 보고하지 않는다.**

현재 검증 작업공간은 여러 overlay를 조립한 것이고 원 프로젝트 전체 파일이 아니다. Full pytest collection에서 다음 기반 모듈 등이 없어 12개 collection error로 중단됐다.
- `app.backtest.audit`
- `app.backtest.history_store`
- `app.backtest.models`

이는 B.2.3.2a 테스트 실패가 아니라 overlay-only 검증 환경의 누락이다.

### Vite production build
실행하지 못했다. 현재 overlay 조립본에는 원 프로젝트 `package.json` 전체가 없다.

### 실제 브라우저
이번 환경에서는 PASS로 보고하지 않는다. B.2.3.1 때부터 headless Chromium이 최소 fixture에서도 종료되지 않는 환경 문제가 확인돼 있다. 사용자 PC 실제 화면 검증이 최종 확인 기준이다.

## 완료 판단
이번 작업으로 "조건 가격대 ↔ 손절구간 overlap" 자체를 계산 버그로 간주하던 해석을 교정했다.

핵심 결론:
1. 화면에서 겹친 5건은 **전략 조건 가격대와 실행 리스크 가격을 같은 의미로 표시한 UX/semantic 문제**였다.
2. 실제 Risk 오류는 Risk Engine의 `entry_price`와 stop/invalidation/target 관계로 별도 판정해야 한다.
3. 가격 숫자와 Ranking은 이번 작업에서 변경하지 않았다.
4. UI에서 `관심 가격`을 `전략 조건 가격대`로 바꿔 사용자가 "매수 가능 구간"으로 오해할 가능성을 줄였다.
5. 다음 실제 Scanner 실행에서 `trace_context`를 통해 해당 종목의 Backend raw 기준을 더 쉽게 추적할 수 있다.

## 버전 정의
`v0.21.4-B.2.3.2a`는 Entry/Stop 공식을 튜닝한 버전이 아니라, **Strategy 조건 가격과 Risk 실행 가격의 역할을 분리하고 실제 오류 판정 기준을 바로잡은 Root Cause Validation 버전**이다.
