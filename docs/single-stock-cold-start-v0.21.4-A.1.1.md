# v0.21.4-A.1.1 Cold Start Path

## Old cold path
1. Fetch KRX market-by-date payload.
2. Normalize the whole market for a single selected stock.
3. Insert market-wide rows into SQLite before proceeding.
4. Wait for a batch's slowest request before starting the next batch.

## New cold path
1. Fetch KRX market-by-date payload.
2. Provider persists the raw full-market payload to its shared raw cache.
3. Filter raw rows by the selected stock code before normalization.
4. Keep a continuous worker pool of up to 12 requests.
5. Persist only the compact selected-stock/index history at the end.

The raw KRX cache, not synchronous market-wide SQLite insertion, is the cross-symbol reuse layer on this request path.
