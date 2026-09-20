# StockScope v0.21.4-B.2.6-A.B — Candidate Quality Discovery

## Goal
Improve the probability that the highest-ranked READY candidates are genuinely better candidates, without changing Production until the signal survives validation.

## Scope in this overlay
1. Quantify READY-score saturation.
2. Define research-only GOOD/BAD labels by within-date 20D-return terciles.
3. Compare current-only features between GOOD and BAD.
4. Evaluate conservative ranking guards without new fitted weights.
5. Split development vs latest-20-date validation chronologically.
6. Check stability across four chronological blocks.
7. Reuse an independent CAP_1_5R snapshot for risk/target guard validation.
8. List high-ranked false positives for follow-up.

## Candidate features
- risk_pct
- structural_target_distance_pct
- relative_strength_market_pct
- price_vs_ma20_pct
- ma20_vs_ma60_pct
- ma60_vs_ma120_pct

Sector RS is excluded because historical Production-safe point-in-time Sector RS is not available in this source snapshot.

## Audit variants
- CURRENT
- RISK_LOW
- TARGET_NEAR
- RISK_Q75_GUARD
- TARGET_Q75_GUARD
- OVEREXTENSION_Q75_GUARD

`OVEREXTENSION_Q75_GUARD` does not invent numeric weights. Within each date it marks a candidate only when at least two of these three current features are in that date's top quartile:
- market relative strength
- price extension above MA20
- MA20 extension above MA60

Marked candidates are demoted behind unmarked peers while current rank order is otherwise preserved.

## Leakage guard
Future 5D/10D/20D outcomes are used only for research labels and evaluation. Variant sorting depends only on current-date features and the existing rank.

## Production guardrail
This overlay must not modify:
- scanner.py
- candidate_priority.py
- Strategy definitions
- Risk / Entry / Stop / Target
- B.2.5-C tie-break
- Historical Evidence policy

## Promotion rule
No Production change unless a current-version focused validation confirms the signal. An old historical snapshot alone cannot approve a Production ranking change.
