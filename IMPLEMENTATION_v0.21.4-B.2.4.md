# StockScope v0.21.4-B.2.4 — Implementation Notes

## Implemented
- `prepare_latest_confirmed_data(..., progress=...)` progress callback 추가.
- latest EOD preparation을 Scanner cancellable job 내부로 이동하여 클릭 직후부터 분석 완료까지 하나의 job stream으로 통합.
- KOSPI/KOSDAQ stock/index, local store, EOD probe, read-back stage를 구분.
- KRX provider await 중 2초 heartbeat 갱신.
- `VERIFIED_REUSE` stage provenance 유지.
- failure stage 및 freshness failure payload를 job progress details에 보존.
- Frontend의 동기 freshness preflight 제거.
- 가짜 overall-percent progress bar 제거.
- 준비 단계 count와 실제 item count만 표시.
- 분석 진입 후 preparation 상세를 한 줄 완료 상태로 축약.
- network request/concurrency/retry는 `진행 상세`로 이동.
- Low-Glare/Dark theme token을 재정의하지 않고 기존 CSS variable만 사용.

## Not changed
- `StockScannerService.VERSION = 0.21.3.5`
- strategy/rank/risk/entry/target/exit policies
- scanner session schema
- Market Store data schema

## Validation in overlay environment
- modified Python files: `py_compile` PASS
- `scannerProgress.ts`: TypeScript compile PASS
- pure progress mapping runtime checks: PASS (ALL/KOSPI/reuse/analysis transition)
- B.2.4 source-contract pytest: PASS in assembled overlay tree

Full application build/runtime UI verification must be run in the user's complete repository because this overlay environment does not contain the full frontend dependency tree.
