# StockScope Technical + Strategy Analysis v0.7

## 구현 범위
- KRX 최근 30거래일 OHLCV 수집
- 날짜별 KRX bulk 응답 gzip 로컬 캐시
- MA5 / MA20
- RSI14
- ATR14 / ATR%
- 20일 거래량비
- 20일 고점/저점
- 단순 pivot 기반 지지/저항 후보
- 고점/저점 상승 구조
- KRX 대표지수 당일 흐름 기반 시장 국면
- Strategy Engine 6종 + NO_TRADE 연결

## 중요한 제한
- KRX Open API는 날짜 단위 bulk API이므로 첫 전략 분석은 여러 날짜를 수집해 수초 걸릴 수 있습니다.
- 같은 날짜의 시장 bulk 데이터는 backend/runtime/krx에 저장하여 재시작 후에도 재사용합니다.
- v0.7 기본 30거래일에서는 MA60/MA120을 충분히 계산할 수 없으므로 해당 값은 비어 있을 수 있습니다.
- 전략 점수는 성공확률/상승확률이 아니라 규칙 조건 적합도입니다.
- 실제 매수/매도/정정/취소 주문은 구현하지 않습니다.
