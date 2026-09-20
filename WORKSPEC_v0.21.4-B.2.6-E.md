# StockScope v0.21.4-B.2.6-E — Frozen Refined Guard Final Confirmation

## Goal
Run one independent holdout confirmation for the B.2.6-D refined overextension rule without changing the rule, Q75 threshold, feature family, strategy exemption, Production Scanner, Ranking, Strategy, Risk, Entry, Stop or Target policy.

## Frozen rule
- Features: market relative strength, price vs MA20, MA20 vs MA60.
- Threshold: same-date READY Q75.
- Overextended: at least 2 available features and at least 2 above Q75.
- Demotion: only READY slots are reordered; demoted READY peers move behind non-demoted READY peers while Production rank remains stable inside each group.
- Exception: `trend_recovery` with exactly 2-of-3 extreme features is not demoted.
- `trend_recovery` 3-of-3 remains demoted.
- Non-READY slots are immutable.
- Frozen fingerprint: `5967c491bbfaa11ca4fa4f8197504813712d08d2b76d76be78ea314b49800579`.

## Independent holdout
- Default 20 dates, approximately 5 from each 2023/2024/2025/2026 block.
- Existing 73 B.2.6-A/B/C dates are excluded.
- New dates must be at least 3 common KOSPI/KOSDAQ trading-day positions away from previous dates.
- Dates are selected deterministically from the local `HistoricalMarketStore` before any holdout outcomes are evaluated, then frozen in `backend/tools/audit_inputs/b26e_holdout_dates.txt`.
- If the exception sample is insufficient, rerunning with `--sample-size 30` preserves the first 20 and adds only 10 dates.

## Evaluation order
1. Recreate Production candidates with Scanner 0.21.3.7.
2. Apply Production ranking including B.2.5-C.
3. Calculate same-date overextension features.
4. Freeze CURRENT and FROZEN_REFINED ranks.
5. Only then read D+1 future rows for 5D/10D/20D outcomes.

## Primary
Top3: 5/10/20D mean/median/positive rate, 20D trimmed mean, mean without best, MFE/MAE, Target1-first and Stop-first.

## Promotion gates
- Top3 20D mean improves.
- Top3 20D trimmed mean does not worsen.
- Top3 20D mean without best does not worsen.
- Top3 MAE20 does not worsen.
- Top3 Target1-first 20D does not worsen.
- Top3 Stop-first 20D does not worsen.
- At least one of 20D median / 20D positive rate / 10D mean / T1-first 10D improves.
- At least 3 of 4 chronological blocks improve either Top3 20D mean or MAE20.
- Minimum sample: 15 overextended candidates and 3 refined-exception opportunities.

## Verdicts
- `PROMOTE_TO_PRODUCTION`
- `KEEP_RESEARCH_ONLY`
- `REJECT_REFINED_GUARD`
- `INSUFFICIENT_FINAL_SAMPLE`

## No tuning
No Q70/Q80 comparison, no new features, no new exemptions, no weights, no ML, no 80D retuning.
