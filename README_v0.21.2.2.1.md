# StockScope v0.21.2.2.1 EntryRiskGuide Signature Hotfix

## 증상
`build_entry_risk_guide() got an unexpected keyword argument 'as_of_date'`

## 원인
v0.21.2 이후 scanner.py / multi_strategy.py 호출부는 `as_of_date`와 `entry_timing`을 전달하지만,
일부 누적 overlay에 최신 `backend/app/backtest/entry_risk_guide.py`가 포함되지 않아
프로젝트에 남아 있던 구버전 Builder와 함수 시그니처가 불일치했습니다.

## 수정
최신 v0.21.1 Concrete Entry & Risk Guide Builder를 복구합니다.
지원 인자:
- as_of_date
- entry_timing

Strategy/Risk/Scanner/Historical/UI 계산 로직은 변경하지 않습니다.

## 검증
- Python py_compile 통과
- Entry Risk Guide unit tests: 23/23 passed
- as_of_date 전달/반환 테스트 포함
- entry_timing rebound_confirmation 재사용 테스트 포함

## 적용
프로젝트 루트에 ZIP 내용을 그대로 덮어씁니다.
