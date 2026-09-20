# v0.21.4-B.2.3.4c.4f.2 — Sector RS Prefetch / Cache Plumbing

## Scope
- c.4f.1 temporal gate 유지.
- Scanner 상위 계층에서 optional sector input을 bulk prefetch.
- current OpenDART metadata는 `STATIC_CURRENT`로 분류해 audit-only.
- BacktestEngine 내부 network I/O 금지.
- KRX 업종지수는 종목별 호출이 아니라 `market + date` 단위 한 번 조회 후 여러 업종이 공유.
- 동일 종목 company metadata는 in-memory cache.
- Production strategy/ranking/RS weights/fallback 변경 없음.
- Scanner version은 0.21.3.4 유지: audit-only path이며 기본 constructor에서는 비활성.

## Performance invariant
`index_daily` 호출 수는 종목 수에 비례하지 않고 필요한 날짜 수에 비례해야 한다.

## Activation
`StockScannerService(..., sector_company_provider=provider)` 또는 테스트용 `sector_prefetcher=`를 명시적으로 주입했을 때만 활성화한다.
기존 API wiring은 변경하지 않는다.
