# StockScope v0.19 — Backtest Engine / Pullback MVP

## 목적

현재 StockScope의 Pullback 전략과 Entry Timing 규칙을 과거 KRX 확정 데이터에 다시 적용해, 전략 적합도와 실제 과거 표본 성과의 관계를 검증한다.

이 기능은 투자수익을 예측하거나 실제 주문을 실행하지 않는다. Strategy Score와 7개 Entry Timing 조건 수는 상승확률이 아니다.

## 데이터 범위

- 사용: KRX 종목 일봉, KRX 대표 시장지수
- 제외: OpenDART 재무, 최신 공시, Investor Style, 실제 계좌/주문
- 이유: 과거 시점에 아직 공개되지 않았던 재무·공시 정보를 사용하면 미래 데이터 누수가 발생할 수 있기 때문이다.
- 업종 상대강도는 v0.19에서 제외한다. 시장 상대강도는 종목과 대표지수의 같은 거래일 KRX 데이터로 재현한다.

## 신호 계산과 미래 데이터 누수 방지

과거 거래일 T를 평가할 때 Technical / Strategy / Pullback Confirmation에는 T까지의 데이터만 전달한다.

```
T 이전 KRX 데이터 + T 확정 EOD
        ↓
TechnicalAnalyzer
        ↓
공용 StrategyInput 매핑
        ↓
StrategyEngine
        ↓
PullbackConfirmationAnalyzer
```

진입 이후의 데이터는 신호를 확정한 뒤 가상 청산을 추적하는 단계에서만 사용한다.

실시간 분석과 백테스트의 StrategyInput 생성 규칙이 따로 변하지 않도록 `app.strategy.context`의 공용 빌더를 사용한다.

## 기본 거래 규칙

- 전략: Pullback
- 기본 최소 Strategy Score: 55
- 실제 기본 진입: Entry Timing 상태가 `REBOUND_CONFIRMED`
- 진입가격: 신호 다음 거래일 시가
- 동일 종목 중복 포지션: 금지
- Stop: Risk Engine의 `invalidation_price`
- Target: v0.19 MVP에서는 Risk Engine `target1_price` 도달 시 전량 가상청산
- Target2: 참고값으로 거래기록에 보존
- 같은 일봉에서 Stop과 Target1이 모두 닿음: 일봉만으로 선후를 알 수 없으므로 보수적으로 Stop 우선
- 다음 날 이후 시가가 Stop/Target을 갭으로 통과: 해당 시가로 청산
- 기간 끝까지 청산 조건 미발생: 마지막 사용 가능 종가로 종료

Target1 전량청산은 부분청산 규칙을 임의로 새로 만들지 않기 위한 v0.19 MVP 정책이다. 향후 청산 규칙을 비교할 때 별도 버전으로 확장한다.

## 최대 보유기간

사용자가 선택한다.

| 선택 | 의미 |
|---|---|
| 5 거래일 | 짧은 반등 중심. 회전은 빠르지만 늦은 추세 회복을 놓칠 수 있음 |
| 10 거래일 | 단기 스윙 중심 |
| 20 거래일 | 기본 추천. 약 1개월 동안 반등/추세 복귀를 기다리는 균형형 |
| 40 거래일 | 중기 회복까지 허용. 자금이 오래 묶이고 단기 Pullback 성격이 약해질 수 있음 |
| 직접 입력 | 1~120 거래일 연구 가능 |

진입일을 1거래일째로 계산한다. Stop/Target이 먼저 발생하면 최대 보유기간 전이라도 즉시 종료한다.

## 거래 비용

사용자가 왕복 비용률(%)을 입력한다. 특정 시점의 세율·증권사 수수료를 코드에 고정하지 않는다.

- Gross: 비용 차감 전 수익률
- Net: `Gross - 사용자 입력 왕복 비용률`

## 결과

### 기본 전략 성과

- 거래 수
- 승률
- 평균 Gross / Net 수익률
- 중앙값 Net 수익률
- 평균 이익 / 평균 손실
- 기대수익
- Profit Factor
- 평균 보유기간
- 최대 연속 손실
- 최대낙폭(MDD)
- 초기/최종 가상 자본
- 누적 Net 수익률

전체 MDD는 단일 포지션·전액 가정의 **일별 종가 mark-to-market** 자산 기준으로 계산한다. 포지션 보유 중에는 입력한 왕복 비용률을 미리 차감한 평가자산을 사용하고, 실제 청산일에는 Stop/Target/기간종료의 실현 Net 결과를 사용한다.

### Strategy Score별 성과

55~69 / 70~79 / 80~89 / 90~100 구간의 실제 거래 결과를 비교한다. 점수를 상승확률로 변환하지 않는다.

### Entry Timing 연구

3/7, 4/7, 5/7, 6/7, 7/7 조건 개수별로 별도의 연구 코호트를 만든다.

이 결과는 `3/7이면 매수` 같은 실전 신호가 아니다. 현재 7개 조건이 실제 과거 표본과 어떤 관계가 있는지 검증하는 연구 데이터다. 기본 실제 백테스트 진입 규칙은 계속 `REBOUND_CONFIRMED`이다.

### 시장환경별 성과

신호일 당시 대표지수 일간 등락으로 현재 Market Regime 규칙을 재사용해 상승/횡보/하락 국면별 성과를 집계한다.

## API

`POST /api/backtest/pullback`

요청 예:

```json
{
  "code": "005930",
  "market": "KOSPI",
  "start_date": "2025-01-01",
  "end_date": "2026-08-31",
  "initial_capital": 10000000,
  "max_holding_days": 20,
  "round_trip_cost_pct": 0.0
}
```

## 성능/데이터 조회 제한

현재 KRX 연결 구조는 날짜별 확정 데이터를 조회하므로 긴 기간의 첫 실행은 많은 요청이 필요할 수 있다.

- v0.19 API는 한 번에 최대 5년으로 제한
- 60거래일 기술지표/상대강도 준비를 위해 요청 시작일 이전 warm-up 기간도 조회
- 기존 gzip KRX 캐시를 그대로 사용하므로 동일 기간 재실행은 더 빨라질 수 있음
- 일부 날짜 조회 실패 시 확보된 데이터로 계산하되 응답 `warnings`와 `data_window`에 상태를 노출

## v0.19에서 하지 않는 것

- Scanner
- 여러 종목 동시 포트폴리오
- 실제 증권 주문
- KIS 주문 연동
- Gemini
- Buffett/Graham/Lynch/CAN SLIM 백테스트
- 전체 전략 일괄 백테스트
- 머신러닝 파라미터 최적화
- 자동 최적 보유기간 선택

보유기간은 사용자가 직접 선택한다. 과거 데이터에 가장 잘 맞는 기간을 자동으로 선택해 제시하지 않아 과최적화 위험을 줄인다.
