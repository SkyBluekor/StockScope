# WORKSPEC v0.21.4-B.2.3.3b — Low-Glare Light Theme Rebalance

## 목적
B.2.3.3a가 순백 surface는 제거했지만 실제 화면의 대부분이 #EEF2F6~#FBFCFE에 머물러 여전히 흰 종이처럼 보이는 문제를 수정한다. Light Theme 자체의 절대 휘도를 낮춰 장시간 분석 화면에서 눈부심을 줄인다.

## 실제 변경
- Page: `#EEF2F6 → #DCE3EA`
- Sidebar: `#F5F7FA → #E5EAF0`
- Surface: `#F7F9FC → #E8EDF3`
- Raised: `#FBFCFE → #EFF3F7`
- Soft/Nested: `#F1F5F9 → #DFE6ED`
- Input: `#F4F7FA → #E3E9EF`
- Selected: `#E8F0FC → #CFDEF3`
- Hover: `#EDF3FA → #D8E1EA`
- Light border/text/status palette도 낮아진 surface에서 WCAG AA 대비가 유지되도록 재조정한다.
- Light topbar는 sidebar 계열 surface를 사용해 화면 상단이 밝은 띠처럼 뜨지 않게 한다.
- Light 기본 카드 shadow를 제거한다. 정보 계층은 shadow가 아니라 surface 명도와 border로 표현한다.

## 절대 비변경
- `html[data-theme="dark"]`의 canonical visual token 값
- Scanner Ranking / Strategy / Risk / Entry / Stop / Invalidation / Target1 / Target2
- B.2.3.3 Decision Consistency
- KRX/OpenDART/Market Store/Backtest/Production Exit Policy

## 회귀 방지
- `lowGlareLightThemeRegression_v0214b233b.py`: B.2.3.3a 대비 실제 luminance 감소, surface hierarchy, WCAG contrast, dark token 보존 검증.
- 기존 `lightThemeRegression_v0214b233a.py`는 superseded 색상값을 고정하지 않고 Light/Dark 구조 자체를 보호하도록 업데이트.
- `themeDecisionRegression_v0214b233.py`는 새 Light page token을 반영하되 Decision Consistency 검증은 그대로 유지.

## 완료 판단
브라우저 실제 화면은 사용자 환경에서 최종 확인한다. 정적 테스트만으로 `시각적으로 충분히 어둡다`고 PASS 처리하지 않는다.
