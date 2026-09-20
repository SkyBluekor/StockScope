# WORKSPEC v0.21.4-B.2.3.2d.1 — Target1 Cap Explainability Completion

## 목표
B.2.3.2d에서 적용된 Production Target1 `min(structural, 1.5R)` 정책의 계산값은 변경하지 않고,
Scanner 상세 화면에서 cap 적용 이유와 원래 구조 목표를 사용자가 바로 이해할 수 있게 표시한다.

## 범위
- Scanner 상세 화면의 1차 목표 영역에 cap 설명 추가
- cap이 실제 적용된 경우에만 표시
- 구조 목표 가격과 구조 목표 basis 표시
- 다른 상세 Entry/Risk 카드의 문구를 동일한 사용자 표현으로 정리

## 표시 규칙
### cap 적용
- `1.5R 현실성 상한 적용`
- `구조 목표 {가격} · {basis}`

### 구조 목표가 1.5R 이하
- cap 안내를 표시하지 않는다.

### 구조 목표가 없고 1.5R fallback 사용
- cap 안내를 표시하지 않는다.
- 기존 `1.5R 기준` 의미를 유지한다.

## Guardrail
변경 금지:
- Target1/Target2 계산값
- rr1/rr2
- Entry/Invalidation/Stop
- Strategy/Ranking/Quick18
- resistance/high20
- Scanner decision version (`0.21.3.6` 유지)

후보 비교 목록은 단순 비교 역할을 유지하며 구조 목표 설명을 추가하지 않는다.
상세 화면에서만 설명한다.
