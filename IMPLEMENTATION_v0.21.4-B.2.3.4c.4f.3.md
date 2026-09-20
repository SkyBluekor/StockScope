# IMPLEMENTATION v0.21.4-B.2.3.4c.4f.3

## Changes
- `sector_rs_prefetch.py`
  - concurrent company metadata fetch bounded by existing concurrency
  - in-process `(market,date)` KRX index-day cache across audit dates
  - `index_cache_hits` metric
- `scanner.py`
  - aggregate prefetch cache-hit metric
- `strategy_integrity_audit.py`
  - prefetch Sector input per market/date when configured
  - pass `sector_input` to `_signal_snapshot`
  - collect audit-only 20D Sector RS coverage and temporal integrity metrics
  - report unavailable reason counts and provider/cache totals
  - preserve Production RS stats separately
- `run_scanner_strategy_integrity_audit.py`
  - `--sector-rs-audit-live` explicit opt-in
  - lazy real KRX/OpenDART provider construction
  - default remains offline-only
- tests
  - prefetch cache reuse
  - audit plumbing source guards

## Local verification in build environment
Focused c.4f tests: 11 passed.
Full StockScope regressions must be run in the user's repository because the build workspace contains an overlay subset, not the complete repository.
