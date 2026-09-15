# StockScope v0.21.4-A.1.1 — Single-Stock Cold Start Throughput Fix

## Why this patch exists
v0.21.4-A.1 improved warm/cache paths, but a never-seen 3-year range could still spend several minutes in KRX preparation. The remaining path normalized the entire market payload and synchronously promoted market-wide rows while a single-stock backtest only needed one symbol.

## Changes
- On both raw-cache hits and true KRX HTTP misses, single-stock backtests call `stock_daily(..., code=<selected>)`.
- The KRX provider still caches the untouched full-market raw response, so a later symbol can reuse the same date without another HTTP request.
- The single-stock request path no longer performs market-wide SQLite promotion with ~1,000 normalized stock rows per fetched day.
- Replaced stop-and-go fetch batches with a continuous 12-worker queue. A slow request no longer blocks an entire batch from starting the next date.
- Compact selected-stock and benchmark histories are still persisted after preparation.
- Backtest progress now exposes `Cold Start Fast Path`, concurrency and retry counts.
- Compatibility fallback remains for legacy/custom providers that do not support the `code` argument.

## Important limit
KRX Open API is still date-based. If the local machine has never fetched a required historical date, that date still needs a real KRX request. This patch removes avoidable local work and improves request utilization; it does not invent a range endpoint that KRX does not provide.

After one complete cold run, the provider raw cache is shared across symbols for the same market/date range. A different stock should therefore reuse those days without new KRX HTTP requests.

## Validation
- Cold-start focused tests: 3/3 passed.
- Relevant cumulative regression set: 94/94 passed.
- Python compile passed.
- BacktestPanel.tsx / api.ts TypeScript syntax transpilation passed.
- Full project production Vite build was not claimed.
