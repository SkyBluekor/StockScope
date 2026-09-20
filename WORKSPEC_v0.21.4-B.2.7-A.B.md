# WORKSPEC v0.21.4-B.2.7-A.B — Entry Stability Discovery

## Goal
Find current-time features that separate READY candidates whose current CAP_1_5R path reaches Target1 first from candidates that hit Stop first.

Primary objective:
- Target1-first 20D higher
- Stop-first 20D lower

Secondary sanity:
- 20D return must not be blindly maximized
- MAE must not deteriorate together with return
- NO_EVENT remains a third label

## Data
- Reuse the original B.2.6 development window only: 53 dates, 2023-01-26..2025-08-12.
- Bundled compact input contains 705 READY candidates and their research-only future outcomes.
- Entry Stability features are recomputed from the user's local HistoricalMarketStore using stock rows <= analysis_date only.
- No KRX/network call.

## Features
1. ATR14 %
2. 20D daily-return standard deviation %
3. 20D maximum drawdown %
4. Close location inside D candle
5. 5-session change in price-vs-MA20 gap
6. D volume / previous-20-session average volume

## Labels
- GOOD_ENTRY = TARGET1_FIRST
- BAD_ENTRY = STOP_FIRST
- NO_EVENT = all other event statuses
- 20D is primary, 10D is retained as supporting evidence.

## Threshold policy
- Same-date READY Q25 / Q75 bands only.
- No optimized numeric threshold search.
- No score weights.
- No B.2.6 overextension feature/flag input.

## Rule smoke
- Discover at most three unstable LOW/HIGH quartile bands.
- A research rule only demotes that unstable band behind other READY peers.
- Existing rank is preserved within stable/unstable groups.
- Production candidate state/action is never changed.

## Verdict
- PROMISING_ENTRY_STABILITY_SIGNAL
- WEAK_ENTRY_STABILITY_SIGNAL
- NO_USEFUL_ENTRY_STABILITY_SIGNAL

## Out of scope
- Production ranking changes
- Scanner/Strategy/Risk/Entry/Stop/Target modifications
- C/E holdout tuning
- ML / regression / grid search
