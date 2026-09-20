# WORKSPEC v0.21.4-B.2.3.4c.4f

## Historical Sector RS Input Plumbing & Temporal Integrity

### Purpose
Restore the missing historical Sector Relative Strength input path without changing strategy weights, ranking, Quick18/Quick36, Market160, risk, entry/stop/target/exit, or MA120 behavior.

### Confirmed precondition
- Normal StrategyService already supports OpenDART industry-code mapping + KRX sector benchmark history + SectorRelativeStrengthAnalyzer.
- Backtest/Scanner currently feeds `relative_strength_sector_pct=None`.
- KRX historical index lookup is as-of/backward only.
- Current OpenDART `company_by_stock_code()` industry metadata has not been proven point-in-time historical metadata.

### c.4f temporal gate
Historical sector mapping is explicitly classified as:
- `POINT_IN_TIME`: may affect Production strategy input.
- `STATIC_CURRENT`: audit-only; MUST NOT affect Production historical strategy input.
- `UNKNOWN`: audit-only.

### This implementation slice
1. Add a deterministic, already-fetched `HistoricalSectorInput` container.
2. Add a second as-of slice at the BacktestEngine boundary so future sector rows are ignored even if supplied by a caller.
3. Reuse the existing `SectorRelativeStrengthAnalyzer`; do not duplicate RS math.
4. Add Production gating: only `POINT_IN_TIME` sector inputs can populate `relative_strength_sector_pct`.
5. Preserve current behavior when no sector input is prepared.
6. Emit audit metadata for temporal status, benchmark, sector-history end date, ignored future rows, and unavailability reason.
7. Add focused tests for 20D calculation, positive/negative temporal gating, insufficient history, and no-lookahead.

### Explicit non-goals
- No Breakout RS weight edits (6+4+8 remains untouched).
- No sector->market fallback policy edit.
- No scanner ranking/selection policy edit.
- No network I/O inside BacktestEngine.
- No Production activation using current OpenDART metadata until point-in-time provenance is demonstrated.

### Next implementation slice after tests
Wire a Scanner/Audit-side bulk prefetcher outside BacktestEngine. The prefetcher must deduplicate by market/date/benchmark and classify current OpenDART metadata as `STATIC_CURRENT` unless a point-in-time source is proven.
