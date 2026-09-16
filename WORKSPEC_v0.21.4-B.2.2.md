# v0.21.4-B.2.2 — Profit Protection & Exit Decision UX

## 목적
실제 Production 매도 기준을 종목별 가격 계획 화면에 연결해, 사용자가 현재 수익 실현 기준·1차/2차 목표의 역할·추적형 수익 보호 적용 여부를 이해할 수 있게 한다.

## 핵심 원칙
- 연구 결과가 아니라 실제 Production mapping을 표시 기준으로 사용한다.
- 현재 기본 정책이면 `1차 목표가 도달 시 전량 매도`를 명확히 표시한다.
- 추적형 정책이 실제 적용된 경우에만 수익 보호 안내를 표시한다.
- 포지션 이력이 없으면 실제 보호선 활성 여부나 보호 가격을 추측하지 않는다.
- 2차 목표가는 기본 정책에서는 참고 가격, 추적형 정책에서는 수익 보호 시작 기준으로 설명한다.
- 사용자 화면에 내부 enum/Exit Policy 용어를 직접 노출하지 않는다.

## Backend
`ProductionExitPolicyEngine.historical_policy_metadata()`에 사용자 UX가 안전하게 판단할 수 있는 수익 보호 metadata를 추가한다.
- `holding_policy`
- `post_target2_horizon_days`
- `policy_source`
- `fallback_used/fallback_reason`
- `profit_protection.enabled`
- `profit_protection.activation`
- `profit_protection.state`
- `profit_protection.current_protection_price`

현재 포지션 이력이 없는 일반 종목 분석에서는 추적형 정책이라도 `POSITION_CONTEXT_REQUIRED`로 반환한다. 실제 보호 가격을 임의 계산하지 않는다.

## Frontend
신규 `ProfitProtectionGuide.tsx`를 추가한다.
- 실제 적용 중인 수익 실현 기준을 가장 먼저 표시
- 기본 정책: 1차 목표가 전량 매도 / 2차 목표가 참고 가격
- 추적형 정책: 2차 목표가 이후 수익 보호 시작 구조 설명
- 현재가가 2차 목표가 이전/이상인지 설명하되 실제 보호 활성 여부는 포지션 이력 없이는 확정하지 않음
- 향후 backend가 `PROTECTION_ACTIVE + current_protection_price`를 제공하면 보호 기준과 현재가 간 거리를 표시
- 손절/진입/1차/2차 목표와 현재가 위치를 한눈에 보는 가격 위치 바 추가

`EntryRiskGuideCard.tsx`
- 기존 `과거 검증 기준` 표현을 제거
- `현재 수익 실현 기준` 중심으로 재구성
- compact Scanner 카드에도 현재 실제 정책을 짧게 표시

## 변경하지 않는 것
- Production mapping 활성화 여부
- Exit 정책 선택 알고리즘
- 손절/진입/목표가 계산식
- 연구 결과
- 부분 익절
- 자동 주문
- 장중 실시간 스트리밍

## 완료 기준
- 현재 Production이 baseline이면 ATR/MA20/확정 저점 보호선이 나타나지 않는다.
- 1차 목표가가 실제 매도 기준임을 바로 이해할 수 있다.
- 2차 목표가는 현재 정책에 맞게 `참고 가격` 또는 `수익 보호 시작 기준`으로 설명된다.
- 추적형 정책을 synthetic 데이터로 렌더링했을 때 각 정책명이 사용자용 문구로 표시된다.
- 포지션 이력 없이 실제 보호 가격을 만들어내지 않는다.
- 기존 Entry/Stop/Target/Scanner/Backtest 계산을 변경하지 않는다.
