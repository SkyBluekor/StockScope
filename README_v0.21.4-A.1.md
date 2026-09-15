# StockScope v0.21.4-A.1 — Single-Stock Backtest Fast Path

## 목적

`종목 찾기 → 자세히 보기 → 백테스트 → 분석`에서 선택 종목 하나의 3년 데이터를 검증할 때, 이미 로컬 KRX raw cache가 있는데도 날짜별 전체 시장 payload를 다시 정규화하고 SQLite Market Store에 재적재하던 warm-path 비용을 제거한다.

화면에 보이던 `1,624 / 1,710`은 1,710개 종목이 아니라 약 3년의 평일에 대해 `선택 종목 일봉 + 시장지수` 두 작업을 날짜별로 준비하던 항목 수였다. v0.21.4-A.1부터 진행률은 거래일 기준으로 표시한다.

## 핵심 변경

- `backend/app/backtest/service.py`
  - raw KRX stock cache가 이미 있는 날짜는 `stock_daily(..., code=<선택종목>)`로 선택 종목 한 행만 정규화한다.
  - cache miss로 실제 새 KRX 데이터를 받은 날짜만 기존처럼 전체 시장 rows를 Market Store에 승격한다.
  - cached index도 단일 종목 분석에서는 compact history에 저장하고 불필요한 날짜별 SQLite rewrite를 피한다.
  - Legacy HistoricalStore를 매 실행마다 SQLite로 bulk import하지 않고 필요한 기간만 memory merge한다.
  - 동일 종목 재실행 시 compact HistoricalStore를 우선 재사용한다.
  - progress를 stock/index item 수가 아니라 거래일 수 기준으로 표시한다.
  - `legacy_load_ms`, `market_store_load_ms`, `history_fill_ms`, `data_prepare_ms`, `cached_symbol_fast_path_hits`, `single_stock_fast_path` diagnostics 추가.
- `backend/app/backtest/market_store.py`
  - `stock_series`, `stock_series_many`, `index_series`의 `day_status` 조회도 요청 기간으로 제한한다.
- `backend/app/market/providers/krx.py`
  - v0.21.0.3의 `stock_daily(..., code=...)`, `has_cached_day()` 지원 파일을 누적 overlay에 포함해 Fast Path 의존성을 명시적으로 보장한다.
- `backend/app/market/kst.py`
  - Windows KST fallback 유지.
- `frontend/src/components/BacktestPanel.tsx`
  - 진행률에서 `단일 종목 Fast Path`, `선택종목 캐시`, `KRX 캐시`, `실제 요청`을 구분한다.
  - 완료 후 개발 확인용 성능 진단에 데이터 준비/10전략 계산/전체 시간을 표시한다.
- `backend/tests/test_single_stock_fast_path_v0214a1.py`
  - cached market day에서 항상 선택 종목 코드만 provider에 전달하는지 검증.
  - 동일 종목 두 번째 실행이 compact history를 재사용하는지 검증.
  - Market Store status 조회가 요청 범위를 지키는지 검증.

## 변경하지 않은 것

- 10개 Strategy 공식/threshold
- Risk 기준
- Entry Timing 기준
- Target1/Target2 의미
- Historical Evidence 계산 정책
- Scanner Ranking
- v0.21.4-A Exit Policy 연구 공식
- Scanner의 Target2 표시 UI
- Profit Protection production 적용
- 주문/실시간 기능

## 기대 효과와 측정 원칙

이 패치는 사용자가 보여준 `실제 요청 0회`인데도 약 258초가 소요되던 warm-cache 경로의 구조적 낭비를 제거한다. 다만 실제 사용자 PC의 KRX cache 크기, 디스크, SQLite 상태와 데이터 기간을 이 빌드 환경에서 그대로 재현할 수 없으므로 `258초 → N초`라고 결과를 단정하지 않는다.

같은 포스코퓨처엠 3년/10전략 분석을 다시 실행해 `데이터 준비`, `10전략 계산`, `전체`, `선택종목 캐시`, `실제 요청`을 비교한다.

## 검증

- 신규 Fast Path 테스트: 3개
- 관련 누적 회귀 묶음: 99/99 통과
  - Single-stock Fast Path
  - Market Store
  - Backtest Performance
  - Scanner Bootstrap Performance
  - Entry Risk Guide
  - Multi Strategy
  - Historical Evidence
  - Candidate Priority
  - Scanner
  - Exit Policy Research
  - Windows KST fallback
- 변경 Python 파일 `py_compile` 통과
- `BacktestPanel.tsx`, `api.ts` TypeScript syntax/transpile 검사 통과

전체 프로젝트 pytest 또는 Vite production build 전체를 통과했다고 주장하지 않는다.
