# v0.21.4-A.1 — Single-Stock Backtest Fast Path

## 문제 재현

사용 흐름:

`종목 찾기 → 후보 자세히 보기 → 백테스트 → 10가지 투자 방법 자동 비교 → 분석`

한 종목만 선택했는데도 약 3년 범위에서 `과거 KRX 데이터 준비 중 1,624 / 1,710`, `실제 요청 0회`, 약 258초가 관찰됐다.

`1,710`은 KRX 종목 수가 아니다. 기존 `_ensure_range()`가 평일마다 stock과 index 두 종류를 각각 work item으로 만들었기 때문에 약 855일 × 2의 진행 단위가 표시된 것이다.

## 실제 병목

기존 warm path에서는 Market Store에 아직 없는 날짜마다 provider를 호출했다. KRX raw gzip cache가 이미 있어 HTTP 요청은 0회였지만, stock payload는 날짜마다 전체 KOSPI/KOSDAQ rows를 로드하고 전부 normalize했다. 이후 전체 시장 rows를 다시 SQLite Market Store에 넣었다.

즉 네트워크가 아니라 다음 반복 비용이 핵심이었다.

1. gzip JSON cache open/decode
2. 전체 시장 rows normalize
3. 선택 종목 한 행 탐색
4. 전체 시장 rows SQLite upsert
5. 약 3년 날짜만큼 반복

## Fast Path

### 이미 raw cache가 있는 stock day

```text
KRX raw gzip day cache
        ↓
raw row에서 code로 먼저 filter
        ↓
선택 종목 1행만 normalize
        ↓
현재 backtest HistorySeries에 추가
        ↓
compact per-symbol HistoricalStore 저장
```

이 경로에서는 전체 시장 SQLite day-complete를 표시하지 않는다. 실제로 전체 시장을 저장하지 않았기 때문이다.

### 실제 HTTP/network miss인 stock day

```text
KRX HTTP
  ↓
전체 시장 payload
  ↓
기존 방식대로 Market Store에 전체 시장 저장
```

새로 다운로드한 데이터는 다른 종목도 재사용할 수 있도록 기존 장점을 유지한다.

### Index

raw index cache가 이미 있는 경우 단일 종목 분석에 필요한 main index row만 compact history에 저장하고 날짜별 SQLite rewrite를 생략한다. 새 network 데이터는 기존 방식대로 persistent Market Store에 저장한다.

## 반복 분석

첫 실행 후에는 `HistoricalStore`에 해당 종목과 index의 compact history가 생긴다. 동일 종목/범위를 다시 분석하면 provider raw cache까지 가지 않고 compact history에서 대부분 해결하도록 한다.

Legacy history는 매 클릭마다 SQLite Market Store에 다시 import하지 않는다. 필요한 bounded window만 memory merge한다.

## 10개 전략 데이터 공유

`MultiStrategyBacktestEngine`은 이미 날짜별 common snapshot을 한 번 만든 뒤 10개 전략에 공유하고 있었다. 따라서 이번 버전은 전략 수식이나 indicator 계산 구조를 불필요하게 다시 작성하지 않는다. 현재 실제 병목인 history preparation path만 최적화한다.

## Progress 의미 변경

기존:

```text
1624 / 1710
```

stock/index work item 각각을 세어서 종목 수처럼 오해하기 쉬웠다.

새 버전:

```text
선택 종목 과거 데이터 준비 중
812 / 855 거래일
```

한 날짜의 stock과 index 준비가 모두 끝났을 때 그 거래일을 완료로 센다.

세부 항목:

- 처리 경로: 단일 종목 Fast Path
- 과거 저장소: compact/Market Store reuse
- 선택종목 캐시: raw KRX cache에서 selected-code path로 처리한 날짜
- KRX 캐시: provider memory/disk/empty-marker hit
- 실제 요청: HTTP request 수

## Performance diagnostics

응답 `performance`에 기존 시간과 함께 다음 진단값을 추가/유지한다.

- `data_prepare_seconds`
- `strategy_calculation_seconds`
- `total_seconds`
- `legacy_load_ms`
- `market_store_load_ms`
- `history_fill_ms`
- `data_prepare_ms`
- `cached_symbol_fast_path_hits`
- `single_stock_fast_path`
- `network_requests`

사용자 PC에서 실제 개선치를 측정할 때 `data_prepare_seconds`가 핵심이다.

## 결과 일관성

Fast Path는 데이터 획득/저장 경로만 바꾼다.

변경 금지:

- Strategy signal formula
- Entry/Exit rule
- Risk threshold
- Target price
- Historical Evidence
- Candidate ranking
- Exit Policy Research formula

같은 날짜/같은 OHLCV라면 전략 결과는 기존과 동일해야 한다.

## 다음 작업과 분리

이번 버전에 포함하지 않는다.

1. Scanner 카드에 Target2 표시
2. v0.21.4-B Profit Protection production 적용
3. 실시간 KIS API
4. 뉴스/미국 시장 context
