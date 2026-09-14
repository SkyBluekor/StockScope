# StockScope v0.20.2.2 — Multi-Strategy Runtime Fix

Small follow-up patch for v0.20.2 / v0.20.2.1.

- Fixes `name 'data' is not defined` during multi-strategy result generation.
- Uses the final backtest snapshot explicitly when formatting current strategy condition details.
- Does not change strategy selection, backtest calculations, Risk Engine rules, or the v0.20.2.1 UI.

Apply this overlay after v0.20.2.1.
