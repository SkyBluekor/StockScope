# StockScope v0.21.4-A.3 — Scanner Result Persistence & Back Navigation

## 목적
완료된 종목 찾기 결과를 상세 분석 이동 때문에 버리지 않습니다. 같은 브라우저 탭/세션에서 Scanner로 돌아오면 기존 후보, 설정, 스크롤 위치와 펼친 3년 근거 상태를 즉시 복원합니다.

## 변경 사항
- 완료된 `ScannerResponse` 전체를 `sessionStorage`에 저장합니다.
- SPA 메모리 스냅샷도 함께 유지해 브라우저 저장소가 차단된 경우에도 같은 실행 중 복귀를 지원합니다.
- `이 종목 자세히 분석` 클릭 직전에 현재 스크롤 위치를 저장합니다.
- Scanner 재진입 시 API를 자동 호출하지 않고 저장 결과를 먼저 렌더링합니다.
- `다른 후보 보기`와 후보별 `과거 근거 자세히 보기` 상태를 복원합니다.
- 같은 설정에서 결과가 있으면 상단 실행 버튼 대신 `분석 결과 유지 중` 상태를 표시합니다.
- 사용자가 명시적으로 `다시 분석`을 눌렀을 때만 강제 Scanner 재실행을 수행합니다.
- 재분석이 실패해도 직전 결과를 지우지 않습니다.
- 시장 범위를 변경하면 기존 세션 결과를 폐기합니다.
- 캐시 schema version 불일치 또는 시장 범위 불일치는 복원하지 않습니다.
- 날짜가 바뀐 세션 결과는 자동 폐기하지 않고, 새 확정 일봉이 있다면 `다시 분석`하도록 안내합니다.

## 변경하지 않은 것
- Scanner 후보 선정/Ranking 계산
- Historical Evidence 계산
- Entry/Risk/Target 계산
- Backtest/Exit Policy
- Backend API/Schema

## 검증
- `scannerSession_v0214a3.ts` 저장/복원/스키마 무효화/시장범위 불일치/메모리 fallback 테스트 통과
- ScannerPanel / scannerSession / api.ts TypeScript transpile syntax 통과
- PostCSS parse 통과
- 기존 v0.21.4-A.2 대비 기존 파일 변경은 `ScannerPanel.tsx`, `styles.css` 두 개뿐
