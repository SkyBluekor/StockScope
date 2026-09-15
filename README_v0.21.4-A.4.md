# StockScope v0.21.4-A.4 — Scanner Price Plan & Entry Position Clarity

Scanner의 추상적인 `진입 기준 거리 0.0%` 표시를 제거하고 현재가가 실제 진입/돌파/관심 가격 기준에서 어디에 있는지 자연어로 설명합니다.

## 변경 범위
- Scanner 우선순위 카드의 `진입 기준 거리` 숫자 박스 제거
- 우선순위 fact에 남아 있던 `거리 x.x%` 사용자 노출 제거
- Scanner compact Entry/Risk 영역을 `가격 계획`으로 재구성
- 현재가 + 현재 가격 위치 문장 표시
- 진입 참고 / 손절 참고 / 1차 목표 / 2차 확장 목표를 한 영역에서 표시
- 2차 확장 목표가 현재 Historical Backtest 청산 정책에 포함되지 않음을 명시
- 현재가 대비 손절/목표 위치를 표시하되 Strategy/Risk/Ranking 계산식은 변경하지 않음

## 변경하지 않은 것
- Candidate Ranking 정렬 공식과 `entry_gap_pct` 내부 값
- Strategy 조건
- Risk threshold와 raw price
- Historical Evidence 계산
- Backtest 거래 생성/Exit 정책
- Scanner persistence
