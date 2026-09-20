# IMPLEMENTATION v0.21.4-B.2.3.4c.4f

## Files
- `backend/app/backtest/sector_rs_input.py` (new)
- `backend/app/backtest/engine.py` (minimal plumbing)
- `backend/tests/test_sector_rs_production_input_v0214b234c4f.py` (new)

## Key behavior
`HistoricalSectorInput` contains already-fetched industry/benchmark metadata and sector rows. It performs no I/O.

`evaluate_historical_sector_input()`:
- re-slices sector rows to `<= signal_date`;
- calls existing `SectorRelativeStrengthAnalyzer`;
- accepts only a 20D primary value for StrategyInput parity with StrategyService;
- exposes audit results for STATIC_CURRENT/UNKNOWN inputs;
- exposes Production sector RS only for POINT_IN_TIME inputs.

`BacktestEngine._signal_snapshot()` accepts optional `sector_input` and threads only Production-safe sector RS into `build_strategy_input()`. The audit-only context is returned separately.

`BacktestEngine.run()` accepts the same optional prepared input and passes it to each signal snapshot. No provider/network dependency was added to the engine.

## Safety properties
- Missing input keeps `relative_strength_sector_pct=None`, preserving existing market fallback semantics.
- Future sector rows are ignored at the engine boundary.
- Current OpenDART metadata cannot silently become historical truth because STATIC_CURRENT is audit-only.
- Strategy weights and policies are unchanged.

## Local artifact verification
The focused helper test suite was run against the reconstructed current SectorRelativeStrengthAnalyzer implementation: 6 passed.
Full repository regression must be run after overlay application because the conversation artifact does not contain the entire repository.
