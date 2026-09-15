# StockScope v0.21.4-A.2 — Backtest Interpretation & Price Accuracy Polish

UI/metadata accuracy patch. Strategy, Risk, target, ranking, trade generation and backtest formulas are unchanged.

## Changes
- Rephrase top strategy as "current closest strategy among 10 methods" instead of implying entry readiness.
- Mark the result date as confirmed EOD.
- Align the `시장 급락 아님` explanation with the actual `TREND_DOWN/PANIC` blocking rule.
- Add explicit historical exit policy metadata: `TARGET1_FULL_EXIT_V1`.
- Explain that Target1 is the current historical backtest exit policy and Target2 is an expansion reference not yet included in historical performance.
- Add KRX tick-aligned display prices while preserving raw prices for all Strategy/Risk/R:R calculations.
- Remove the misleading fixed "5 trades" UI statement and explain historical evidence using the backend status plus sample/return/PF/MDD context.

## Regression rule
Raw Strategy/Risk values must remain unchanged. Display rounding is presentation-only.
