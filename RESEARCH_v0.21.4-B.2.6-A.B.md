# B.2.6-A/B Research Result

## Verdict
`PROMISING_SIGNAL_NOT_PRODUCTION_READY`

Production changed: **False**

## Data used
Primary feature/outcome source:
- strategy-integrity audit source scanner: `0.21.3.5`
- READY candidates: 926
- dates with READY candidates: 73
- chronological development: 53 dates
- latest validation: 20 dates

Independent policy-aware check:
- Target1 realism audit using `CAP_1_5R`
- 18 dates with READY candidates
- 209 READY candidates

These are research snapshots. They are not presented as a current `0.21.3.7` 80-day Production re-run.

## Finding 1 — Ranking score saturation is real
Among the 926 READY candidates in the primary source:
- Strategy Fit = 120: **100%**
- Internal Rank = 108: **100%**
- Baseline quick score = 120: **100%**

So these three values cannot distinguish READY peers in this sample.

## Finding 2 — GOOD candidates are often less overextended
GOOD = within-date top third of 20D return.
BAD = within-date bottom third of 20D return.

Median feature values:

| Feature | Dev GOOD | Dev BAD | Latest-20 GOOD | Latest-20 BAD |
|---|---:|---:|---:|---:|
| risk_pct | 3.90 | 4.65 | 5.17 | 5.41 |
| structural target distance % | 7.09 | 8.75 | 9.69 | 8.71 |
| market RS % | 4.46 | 6.55 | 2.79 | 7.56 |
| price vs MA20 % | 0.39 | 0.83 | 0.80 | 1.62 |
| MA20 vs MA60 % | 4.78 | 7.46 | 8.44 | 14.37 |
| MA60 vs MA120 % | 3.81 | 3.40 | 7.09 | 12.00 |

The most repeatable recent separation is not “higher momentum is always better.” Among candidates that are already READY, excessive RS/MA extension can be a warning sign.

## Finding 3 — latest-20 validation Top3

| Variant | 10D mean | 20D mean | 20D median | 20D positive | MFE20 | MAE20 |
|---|---:|---:|---:|---:|---:|---:|
| CURRENT | -0.58% | -0.34% | -1.54% | 44.1% | 22.17% | -14.62% |
| RISK_Q75_GUARD | -0.37% | +1.18% | -1.54% | 45.8% | 20.41% | -12.30% |
| TARGET_Q75_GUARD | -0.25% | +1.21% | -1.23% | 45.8% | 19.75% | -12.45% |
| OVEREXTENSION_Q75_GUARD | +0.19% | **+3.30%** | **+0.14%** | **50.8%** | 20.94% | **-11.78%** |

## Finding 4 — time stability is not perfect
OVEREXTENSION_Q75_GUARD Top3 20D mean vs CURRENT:

| Block | Range | CURRENT | Guard | Current MAE | Guard MAE |
|---:|---|---:|---:|---:|---:|
| 1 | 2023-01-26..2023-11-15 | +0.94% | +0.56% | -8.66% | -8.33% |
| 2 | 2023-12-01..2024-10-16 | -1.94% | +0.28% | -11.42% | -9.32% |
| 3 | 2024-11-01..2025-09-16 | +2.95% | +4.50% | -7.83% | -6.57% |
| 4 | 2025-10-02..2026-08-18 | -0.74% | +2.94% | -15.22% | -12.34% |

Return improved in 3/4 blocks and MAE improved in 4/4, but one return block regressed. That is enough to investigate, not enough to ship.

## Finding 5 — risk-only promotion is not safe
Independent CAP_1_5R Top3 20D:

| Variant | Target1-first | Stop-first | MAE20 |
|---|---:|---:|---:|
| CURRENT | 52.8% | 47.2% | -8.75% |
| RISK_Q75_GUARD | 37.7% | 62.3% | -9.05% |
| TARGET_Q75_GUARD | 49.1% | 50.9% | -8.79% |

So “lower risk first” or “nearer target first” must not replace the whole Production ranking. This also supports keeping B.2.5-C narrow.

## Decision
No Production change in B.2.6-A/B.

Next experiment should be **one focused current-version 20-date validation** of overextension features. Do not run a broad new 80-day audit yet. If the current-version 20-date result reproduces the benefit, then move to B.2.6-C Candidate Quality v1 design.
