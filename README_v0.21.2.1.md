# StockScope v0.21.2.1 — Quick Analysis Dark UI Consistency Polish

## 기준
- v0.21.2 Scanner Historical Evidence 기능을 그대로 유지한다.
- Strategy / Risk / Entry Timing / Historical 계산 로직은 변경하지 않는다.
- 빠른 조회 화면의 다크모드 가독성·테마 일관성만 수정한다.

## 수정
- 종목 검색 dropdown의 종목명 대비, 보조정보, 시장 badge, 선택 action hierarchy 정리
- 검색 행 hover/focus와 긴 종목명 overflow 처리
- `내 현재 상태 가정`의 white island 제거
- 선택/비선택 position mode를 theme surface 기반으로 통일
- position result/action 하위 카드의 light-only hard-code 제거
- response guide / invalidation helper 카드도 theme variable 기반으로 통일
- 900/560px 이하 검색 결과 레이아웃 보강

## 미변경
- Scanner ranking
- Historical Evidence 계산
- Risk 기준
- Strategy 계산식
- Backend / API schema

## 비교 테스트
동일 종목을 v0.21.2와 v0.21.2.1에서 각각 빠른 조회한 뒤 다음을 비교한다.
1. 검색 결과에서 종목명이 즉시 읽히는지
2. KOSPI/KOSDAQ badge가 과도하게 밝지 않은지
3. `내 현재 상태 가정`이 dark surface로 유지되는지
4. 선택 카드가 blue border/tint로만 강조되는지
5. 결과/위험/도움말 카드에 white island가 남아 있지 않은지
6. 카드·dropdown border가 잘리거나 가로 스크롤이 생기지 않는지
