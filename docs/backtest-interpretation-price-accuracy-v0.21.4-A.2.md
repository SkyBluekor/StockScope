# v0.21.4-A.2 interpretation rules

1. Strategy rank is comparative priority, not an entry signal or probability.
2. Current historical policy remains `TARGET1_FULL_EXIT_V1`.
3. Target2 is shown as `2차 확장 목표` and is not included in current historical performance.
4. `시장 급락 아님` means the market is neither `TREND_DOWN` nor `PANIC`.
5. Raw price values remain the calculation source. Tick-aligned display values are UI-only.
6. Historical sample wording does not hard-code one sample threshold in the UI; the backend historical status remains authoritative.
