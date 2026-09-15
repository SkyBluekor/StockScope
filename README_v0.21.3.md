# StockScope v0.21.3 — Scanner Candidate Ranking & Priority Explanation

## 변경 내용

- 기존 Scanner 후보 풀에 3년 동일전략 Historical Evidence를 붙인 뒤 최종 우선순위를 계산합니다.
- 최종 비교 순서는 `현재 조건 → Risk → 진입 근접도 → 3년 과거 근거 → 전략 적합도`입니다.
- 새 가중치 합산 점수나 상승 확률은 만들지 않습니다.
- 과거 근거가 좋아도 현재 조건 실패를 통과로 바꾸지 않습니다.
- 전략 조건이 모두 맞아도 Risk가 나쁘면 `위험 때문에 보류` Tier로 내려갑니다.
- Scanner 카드에 `왜 N위인가요?`와 강점/현재 사실/감점 근거를 표시합니다.
- 기존 preliminary 순위와 최종 순위 비교는 diagnostics에만 보존합니다.
- v0.21.2.2 Action Plan Readability 및 v0.21.2.2.1 EntryRiskGuide signature fix를 포함한 누적 overlay입니다.

## 검증

- Candidate Priority 신규 테스트: 10 passed
- Entry Risk Guide + Historical Evidence + Multi Strategy + Scanner 포함 관련 회귀: 73 passed
- Python compile: 통과
- ScannerPanel.tsx / api.ts TypeScript syntax diagnostics: 0 errors
- styles.css PostCSS parse: 통과

전체 저장소 full pytest와 Vite production build는 이 overlay 조립 환경에서 수행하지 않았습니다.

## 확인할 화면

Scanner를 실행해 Top 후보 카드에서 아래를 확인합니다.

1. `왜 N위인가요?`
2. `현재 진입 후보 / 진입 후보 가까움 / 조건 확인 필요 / 위험 때문에 보류`
3. 현재 조건과 Risk가 과거 근거보다 먼저 작용하는지
4. 과거 근거 약함/표본 부족이 현재 조건 자체를 FAIL로 바꾸지 않는지
5. 조건 100% + Risk 경고 후보가 조건 근접 + Risk 정상 후보보다 억지로 위에 오르지 않는지
