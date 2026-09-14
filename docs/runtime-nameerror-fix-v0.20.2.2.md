# v0.20.2.2 Runtime NameError Fix

## Symptom
Multi-strategy backtest could fail after completion of historical calculation with:

`name 'data' is not defined`

## Cause
v0.20.2 added beginner-friendly current/required condition measurements. In `MultiStrategyBacktestEngine._run_strategy`, the result-building block referenced `data` even though that local name only existed in `_current_risk_plan`. It also relied on the loop variable `snapshot` remaining bound to the last iteration.

## Fix
The current-condition details now explicitly use the already-selected latest snapshot:

- `latest_data = latest["strategy_input"]`
- `latest_technical = latest["technical"]`

Both passed and unmet condition details use these values. Strategy rules, Risk Engine behavior, UI layout, and backtest calculations are unchanged.
