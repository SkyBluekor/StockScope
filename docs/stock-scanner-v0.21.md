# StockScope v0.21 — Stock Scanner & Candidate Finder

## 목적
사용자가 먼저 종목을 고르지 않아도 KOSPI/KOSDAQ 일반 주식을 빠르게 검사하고, 현재 전략 준비도·Risk·시장환경·과거 근거를 함께 확인해 먼저 볼 후보를 최대 5개 제시한다.

## 파이프라인
1. HistoricalMarketStore에서 최근 약 485일 시장 데이터를 준비한다. 같은 시장/날짜 데이터는 모든 종목이 공유한다.
2. 우선주·SPAC·ETF/ETN·거래정지/거래 없음 종목을 제외한다.
3. 최근 거래대금 기준으로 빠른 유동성 필터를 수행한다.
4. 시장별 상위 유동성 종목에서 최신 60+ 거래일을 이용해 현재 10개 전략 상태를 빠르게 계산한다.
5. 현재 상태가 앞선 종목만 상세 검증 대상으로 좁힌다.
6. 상세 후보는 1년 구간에서 기존 MultiStrategyBacktestEngine으로 10개 전략, 공통 Risk Engine, 과거 근거를 재검증한다.
7. 상승 확률이 아닌 확인 우선순위로 정렬하고 기본 5개만 표시한다.

## 사용자 원칙
- 후보 1위도 진입 조건이 부족하면 `신규 진입하지 않기`로 안내한다.
- 아무 종목도 기준을 만족하지 않으면 후보를 억지로 채우지 않는다.
- 내부 ranking score는 확률로 노출하지 않는다.
- 부족 조건은 현재값/필요값이 있는 경우 그대로 보여준다.
- `이 종목 자세히 분석`은 기존 10전략 백테스트 화면으로 연결한다.

## API
`POST /api/backtest/scanner/jobs`

기본 요청:
```json
{
  "market_scope": "ALL",
  "candidate_limit": 5,
  "force_refresh": false
}
```

기존 백테스트 job polling/cancel API를 재사용한다.

## API Budget
Scanner 데이터 준비도 v0.20.3의 `KrxProvider` Budget Manager와 `HistoricalMarketStore`를 사용한다. 같은 날짜 시장 데이터가 이미 있으면 신규 KRX 요청 없이 재사용하며, 예상 신규 요청이 안전 Budget을 넘으면 실행 전에 차단된다.

## 결과 캐시
같은 기준일/시장/후보 수 조합은 `backend/runtime/scanner`에 결과를 저장한다. 최신 확정 데이터가 바뀌면 새 날짜 키로 다시 계산하며 사용자가 `최신 데이터로 다시 찾기`를 누르면 cache를 무시한다.
