# SC-UX-MOTION-S1 — 종목 찾기 애니메이션 UI 검증

- 기준: Scanner/UI 상태 표시만 변경. Backend Scanner 전략/순위/Risk, Prospective DB, JEV Provider, 비용 승인 규칙 무변경
- 구현 범위: P0. 기존 진척 단계 코드를 재사용한 사용자용 3단계 표시, 신규 결과 첫 등장, JEV 실제 검토 상태 카드, 동작 감소 접근성
- 기존 파일 활용: `ScannerPanel.tsx`, `scannerProgress.ts`, `scannerProgress.css`, `scannerUX.css`, `ScannerAiReview.tsx`.
- 신규 컴포넌트: `ScannerMotionProgress.tsx` (백엔드 상태를 직접 전달받는 렌더링 컴포넌트)
- 신규 테스트: `frontend/tests/scannerMotion.test.mjs`; `npm run test:sc-ux-motion` 및 CI 포함

## 상태·애니메이션 대응

| 실제 데이터 | 사용자 표시 | 허용 효과 |
|---|---|---|
| Scanner queued / scanner_prepare_* | 시장 데이터 확인 | 진행 단계 하나에만 약한 흐름 |
| Scanner scanner_quick_filter / deep_analysis | 종목 분석 | 이전 단계 완료, 현재 단계만 흐름 |
| Scanner scanner_priority_rank | 결과 정리 | 현재 단계만 진행 |
| Scanner completed | 모든 단계 완료 | 진척 애니메이션 정지 |
| Scanner failed / cancelled | 실패·중단 | 완료된 것으로 소급하지 않음 |
| 신규 foreground Scanner result | 후보 목록 최초 등장 | 상위 5개에 65ms 간격 미세 이동/불투명도 |
| 재진입 복원·반복 polling·후보 선택 | 이전 결과 유지 | 재등장 없음 |
| JEV feature pending / not requested | AI 모델 미실행/미제공 | 모델 실행 애니메이션 금지 |
| 로컬 LOCAL_COMPLETE | 기본 근거 확인 완료 | 모델 결과로 표시 금지 |
| 검증된 저장 JEV 리뷰 | 실제 AI 검토 결과 | 완료된 결과만 확인 표시 |
| 실제 검토 RUNNING 기록 | AI 진행 중 | 서버 기록이 있을 때만 아주 약한 펄스 |

JEV 사용 여부는 `scannerAiReviewStatus.ts` 및 실제 저장 리뷰의 ID·무결성·모델 동일성 판정을 사용한다. `LOCAL_MATCH`는 JEV 모델 호출 성공을 뜻하지 않는다. Backend가 `BASELINE_ONLY`, `NOT_REQUESTED`를 반환하면 반드시 모델 미실행으로 표현한다.

## 표시와 접근성

- 기본 화면: 3단계 진행 흐름과 현재 작업; 7+4 기술적 단계는 '세부 진행 단계 보기'에 포함한다.
- JEV 기본 화면: 실제 모델 검토 여부와 상태 이유; 캡처 ID 등 상세 근거는 '검토 출처와 근거 자세히 보기'로 숨긴다.
- 색상만으로 상태를 판별하지 않고 단계마다 '진행 중/완료/대기/실패/중단' 문구를 함께 표시한다.
- `prefers-reduced-motion: reduce`일 때 후보 등장·진행 링·기존 AI 흐름 애니메이션을 모두 끈다.
- 별도의 Timer를 이용한 가짜 진행 표시, AI Provider 호출, 광고성 화려한 효과를 추가하지 않는다.

## 테스트 및 UAT

1. `cd frontend; npm run test:sc-ux-motion`
2. `npm run test:sc-ux3` — 기존 JEV 상태 진실성 검증
3. `npm run build`
4. GitHub CI: Backend Python 3.11/3.14, Frontend Node 22, Fresh Clone Windows
5. 실사용 브라우저에서 진행 흐름, 상위 5개 한 번만 등장, 재진입 결과 정지, 모바일 뷰, 모션 감소 설정을 직접 육안 검수한다.

**주의:** CI와 정적/단위 테스트가 통과해도 실제 브라우저 시각/성능 UAT 전까지 '최종 UX 완료'라고 선언하지 않는다.

## 후속 P1

- 탭 전환 및 가격 확인 업데이트의 의미 있는 미세 모션
- 후보 비교 영역 부드러운 펼침
- 모바일 시각/접근성 검수 이후 필요한 부분만 개선
