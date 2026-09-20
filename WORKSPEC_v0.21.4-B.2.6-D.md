# StockScope v0.21.4-B.2.6-D — Overextension Risk / Momentum Split

## Goal
Split the B.2.6-C overextension family into risky overextension versus momentum continuation without tuning Q75 or changing Production.

## Frozen inputs
- Development: first 53 dates from the existing B.2.6-A/B compact baseline.
- Validation: latest B.2.6-C current-version JSON (`Scanner 0.21.3.7`, 20 valid dates).
- No Scanner rerun in this step.

## Candidate rules
1. `OVEREXTENSION_Q75_GUARD`: current research control; demote every >=2-of-3 overextended READY candidate.
2. `TRIPLE_ONLY_GUARD`: demote only 3-of-3 overextension.
3. `TREND_RECOVERY_2OF3_EXEMPT`: demote >=2-of-3 except `trend_recovery` with exactly 2-of-3; 3-of-3 remains demoted.

The refined exception is selected from development evidence only, before current-version validation is scored.

## Research labels
Within each development date among READY candidates:
- top 20D-return tercile = `MOMENTUM_CONTINUATION`
- bottom tercile = `RISKY_OVEREXTENSION`
- middle = `NEUTRAL`

Labels are analysis-only and never ranking inputs.

## Primary metrics
Top3:
- 20D mean / median / trimmed mean / mean without best
- positive rate
- MFE20 / MAE20
- Target1-first 20D
- Stop-first 20D

## Success gate
`REFINED_GUARD_READY_FOR_CONFIRMATION` requires refined Top3 versus CURRENT:
- 20D mean improved
- trimmed mean improved
- mean without best nonworse
- MAE20 nonworse
- Target1-first nonworse
- Stop-first nonworse

## No-touch scope
No changes to Scanner, candidate_priority, Strategy, Risk, Entry, Stop, Target1/2, READY gate, Q75 threshold or feature weights.
