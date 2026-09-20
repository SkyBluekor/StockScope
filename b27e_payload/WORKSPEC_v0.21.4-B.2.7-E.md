# v0.21.4-B.2.7-E — Frozen Volume-Low Guard Fresh Holdout

## Goal
Run the already-frozen `VOLUME_LOW_GUARD` on 20 deterministic, previously unseen dates. Do not retune the rule from the result.

## Frozen rule
- feature: `volume_ratio_prev20`
- formula: D volume / arithmetic mean of the previous 20 sessions
- threshold: same-date READY Q25
- comparison: `<= Q25`
- scope: READY only
- action: move LOW-volume READY candidates after other READY candidates
- within-group order: current Production order
- non-READY slots: immutable

## Freshness
- exclude all B.2.7 development/current-validation dates (73 unique)
- also exclude the B.2.6-E final holdout dates (20 unique)
- unique excluded dates: 93
- keep >=3 common trading-session spacing from every excluded date
- keep >=3 common trading-session spacing among selected holdout dates
- require >=20 future common trading sessions after every selected date
- selection must be deterministic and must not inspect outcomes

## Primary gates
Top3 must satisfy all:
1. Target1-first 20D strictly improves
2. Stop-first 20D strictly improves
3. mean event-R 20D strictly improves
4. 20D mean return does not worsen by >=1.0pp
5. MAE20 does not worsen by >=1.0pp

Robustness additionally checks WIN>=LOSS, GOOD_SWAP>=BAD_SWAP and non-destructive Top1 changes.

## Verdicts
- `PROMOTE_VOLUME_LOW_GUARD`
- `KEEP_RESEARCH_ONLY`
- `REJECT_VOLUME_LOW_GUARD`

Only `PROMOTE_VOLUME_LOW_GUARD` may proceed to B.2.7-F Production integration.

## Safety
Current and guard rankings plus a ranking-freeze hash are completed before D+1 rows are read. Scanner/Ranking/Strategy/Risk/Entry/Stop/Target production files are not modified.
