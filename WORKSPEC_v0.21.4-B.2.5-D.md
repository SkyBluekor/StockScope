# v0.21.4-B.2.5-D — NO_TRADE / Weak-Market Sanity

## 목적
시장이 약하거나 후보 조건/Risk가 부족한 날에도 Scanner가 Top N을 채우기 위해 WATCH/WAIT 후보를 READY/ENTRY_CANDIDATE로 강제 승격하는지 확인한다.

## 범위
- READY / WATCH / action / Risk / missing-condition 일관성
- READY=0 날짜의 ENTRY_CANDIDATE 강제 생성 여부
- 대표 weak-market / Risk-gate 날짜 자동 선택
- 기존 historical strategy audit 재사용

## 비범위
- Strategy 조건 변경
- Risk 계산식 변경
- Ranking B.2.5-C 변경
- Entry/Stop/Target 변경
- 새로운 시장 약세 필터 추가

## 완료 조건
- READY + missing > 0 = 0
- READY + bad Risk = 0
- ENTRY_CANDIDATE + non-READY = 0
- READY=0 + forced ENTRY = 0
- 대표 weak-day에서 WATCH/WAIT 상태 보존 확인
