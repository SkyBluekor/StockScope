# WORKSPEC v0.21.4-B.2.3.3a — Soft Light Theme System Tuning

## 목적
B.2.3.3에서 복구한 Light/Dark 토글은 유지하되, Light 화면의 순백 면적과 반복되는 흰 카드로 인한 눈부심을 줄인다. Dark 화면은 기존 색을 유지한다.

## 변경
- Light page `#EEF2F6`
- sidebar `#F5F7FA`
- base surface `#F7F9FC`
- raised surface `#FBFCFE`
- nested/soft surface `#F1F5F9`
- input surface `#F4F7FA`
- selected `#E8F0FC`, hover `#EDF3FA`
- border subtle/default/strong 계층 추가
- Light의 legacy `--surface-muted`를 soft surface로 연결
- Dark에서는 기존 legacy alias를 raised surface로 명시해 기존 시각값 보존
- legacy input 규칙을 Light 전용 late override로 눌러 input을 카드와 구분
- Light shadow를 작은 1px 수준으로 낮춤
- metadata 색은 페이지 배경에서도 WCAG AA 대비가 나오도록 `#607083` 사용

## 비변경
Scanner/Strategy/Risk/Entry/Stop/Target/Backtest/Ranking/Decision Consistency/KRX/OpenDART/Market Store 로직은 변경하지 않는다.

## 검증
- `themeDecisionRegression_v0214b233.py`
- `lightThemeRegression_v0214b233a.py`
- Dark canonical token 값 보존 검사
- Light surface 5단계 값 중복/순백 금지 검사
- 주요 텍스트 대비 4.5:1 이상 정적 검사

실제 브라우저 시각 검증은 사용자 환경에서 별도로 확인한다. 실행하지 않은 브라우저 검증은 PASS로 기록하지 않는다.
