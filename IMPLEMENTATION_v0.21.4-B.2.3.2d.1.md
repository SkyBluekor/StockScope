# IMPLEMENTATION v0.21.4-B.2.3.2d.1

## 구현
### `frontend/src/components/ScannerPanel.tsx`
- `targetCapExplanation()` 추가
- `target1_cap_applied === true` 이고 `structural_target1_price`가 있을 때만 설명 생성
- 상세 가격 밴드의 1차 목표 셀 아래에 다음 두 줄을 표시
  - `1.5R 현실성 상한 적용`
  - `구조 목표 XX,XXX원 · <structural basis>`
- 후보 비교 목록(`CandidateCompareRow`)은 변경하지 않음
- cap이 적용된 경우 header basis는 audit의 오래된 basis보다 Production cap metadata를 우선해 `1.5R`로 표시

### `frontend/src/components/EntryRiskGuideCard.tsx`
- 기존 cap 설명을 동일한 사용자 문구로 정리
  - `1.5R 현실성 상한 적용 · 구조 목표 ...`

## Backend
변경 없음.
B.2.3.2d가 이미 제공하는 다음 metadata를 그대로 사용한다.
- `target1_cap_applied`
- `structural_target1_price`
- `display_structural_target1_price`
- `structural_target1_basis`

Frontend에서 Target1/cap 여부를 역산하지 않는다.

## 기대 예시 — 한미사이언스 008930
- 1차 목표: 52,200원
- 현재가 대비: +7.65% · 1.50R
- `1.5R 현실성 상한 적용`
- `구조 목표 61,000원 · 최근 저항 후보`
- 2차 목표: 62,200원

## 검증
- ScannerPanel TypeScript syntax/type harness: PASS
- B.2.4a의 기존 TypeScript build-fix 코드가 유지되는지 diff로 확인
- Backend/Production 계산 파일 변경: 0
- 전체 사용자 repo `npm --prefix frontend run build`: 사용자 PC 적용 후 확인 필요
