# StockScope Strategy Engine v0.6

## 핵심 원칙

- 전략 점수는 **수익 확률이 아니라 조건 적합도**입니다.
- 실제 주문 기능과 연결하지 않습니다.
- 전략 엔진은 `StrategyInput`에 들어온 계산 완료 데이터만 평가합니다.
- 종목 데이터 부족, 중요 이벤트, 유동성 부족, PANIC 국면은 `NO_TRADE`가 우선합니다.

## V1 전략

1. Trend Following
2. Pullback
3. Breakout
4. Support Bounce
5. Oversold Bounce
6. Range Trading
7. NO_TRADE

## 주의

현재 임계치는 V1 rule freeze용 초기값입니다.
향후 백테스트에서 성과를 검증하고 walk-forward / out-of-sample 결과를 기준으로 조정합니다.
임계치를 과거 수익률에 맞춰 무한히 최적화하지 않습니다.
