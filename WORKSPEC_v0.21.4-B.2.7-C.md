# StockScope v0.21.4-B.2.7-C — Current-Version Entry Stability Validation

## Goal
Validate only the three rules discovered in B.2.7-A/B on the fixed current-version 20-date set.

## Frozen rules
- VOLUME_LOW_GUARD: same-date READY `volume_ratio_prev20 <= Q25` demoted.
- RETURN_STD_HIGH_GUARD: same-date READY `return_std_20d_pct >= Q75` demoted.
- MA20_GAP_CHANGE_HIGH_GUARD: same-date READY `ma20_gap_change_5d_pct >= Q75` demoted.

No new features, threshold search, strategy exceptions, weights, combinations, or Production policy changes are allowed.

## Primary objective
Top3 20D:
1. Target1-first must increase.
2. Stop-first must decrease.

Return and MAE each have a -1.0 percentage-point protection band versus CURRENT.

## Validation set
Fixed 20 dates reused from B.2.6-C, current Scanner `0.21.3.7` only.

## Outputs
- JSON / CSV / Markdown under `backend/runtime/quality_audit/entry_stability_validation/`
- Per-rule PASS / WEAK / FAIL
- Overall survivor verdict
- Ranking impact and avoided-STOP / demoted-TARGET examples
