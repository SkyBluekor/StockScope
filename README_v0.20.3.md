# StockScope v0.20.3 — KRX API Budget & Historical Market Store

## 목적
백테스트가 같은 KRX 날짜 데이터를 종목마다 반복 요청하지 않도록 시장+날짜 단위 SQLite 저장소를 추가하고, 실제 KRX HTTP 요청을 일일 안전 Budget으로 보호합니다.

## 핵심 변경
- `backend/runtime/market_history/market_history.db`에 시장 전체 일별 데이터를 저장합니다.
- 기존 종목별 `backend/runtime/backtest/history` GZIP 데이터는 요청 시 SQLite로 재사용합니다.
- 기존 `backend/runtime/krx` 원본 GZIP 캐시는 SQLite miss에서 네트워크 없이 재사용·승격합니다.
- 같은 KOSPI/KOSDAQ 날짜를 다른 종목이 다시 분석할 때 시장 데이터를 공유합니다.
- 실제 KRX HTTP 시도는 `backend/runtime/krx/budget.sqlite3`에 날짜별로 영속 기록합니다.
- 기본 안전 상한은 8,000회/일이며 `KRX_DAILY_SAFE_LIMIT` 환경변수로 변경할 수 있습니다.
- 백테스트는 네트워크 요청 전에 SQLite/기존 캐시를 확인해 예상 신규 요청량을 계산하고 안전 상한 초과 예상 시 시작하지 않습니다.
- 같은 endpoint+날짜의 동시 요청은 in-flight de-duplication으로 한 요청을 공유합니다.
- 오늘/최근 빈 응답을 장기 확정 데이터로 고정하지 않는 기존 freshness 정책을 유지합니다.

## 사용 시 주의
`오늘 KRX(앱 기록)`은 v0.20.3 이후 StockScope가 직접 보낸 요청만 기록합니다. 같은 API Key를 다른 프로그램에서 사용한 호출이나 v0.20.3 설치 전 당일 호출량은 알 수 없으므로 8,000회 안전 상한에 여유를 둡니다.

## 기대 효과
첫 3년 동기화는 KRX가 날짜 단위 API이므로 여전히 많은 요청이 필요할 수 있습니다. 대신 한 번 저장한 KOSPI/KOSDAQ 시장 데이터는 다른 종목과 10개 전략이 재사용하므로 이후 동일 기간 분석의 KRX 요청을 거의 0에 가깝게 줄이는 것이 목표입니다.

## 변경하지 않은 것
전략 조건, Risk Engine, 진입/청산 규칙, Strategy Selector 순위 로직은 변경하지 않았습니다.
