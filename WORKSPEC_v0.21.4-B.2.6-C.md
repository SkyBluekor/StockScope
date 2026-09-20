# StockScope v0.21.4-B.2.6-C — Current-Version Overextension Validation

## Goal
Re-run the exact B.2.6-A/B validation dates on current Production Scanner `0.21.3.7` and compare only:

- CURRENT Production ranking (including B.2.5-C)
- OVEREXTENSION_Q75_GUARD

No feature search, weight search, threshold tuning, READY/Strategy/Risk/Target changes, or 80D rerun.

## Fixed guard
Within same-date READY candidates, compute Q75 for:
- market relative strength
- price vs MA20
- MA20 vs MA60

A candidate is `overextended` only when at least 2 available features are above their same-date READY Q75. Only READY slots are reordered; non-READY slots never move.

## Fixed dates
Uses the same held-out 20 dates as B.2.6-A/B (`2025-08-29` .. `2026-08-18`) so version/policy changes are isolated from sampling changes.

## Primary decision
Top3 20D mean must improve, MAE20 must not worsen, Stop-first 20D must not worsen, at least one secondary metric must improve, and outlier-resistant checks must not worsen. At least 3 dates must have Top3 order changes before Promotion is allowed.
