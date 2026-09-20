# WORKSPEC v0.21.4-B.2.3.2d.2 — Target1 Cap Metadata Wiring Fix

## Goal
Restore Target1 cap explainability metadata across the actual Scanner payload path without changing any decision value.

Observed UI state for Hanmi Science (008930 / 2026-09-18):
- current: 48,500
- Target1: 52,200 / 1.50R
- Target2: 62,200
- missing UI explanation: `1.5R 현실성 상한 적용`, structural target 61,000 / recent resistance.

## Scope
Trace/fix only:
`RiskPlan -> entry_risk_guide.risk -> Scanner candidate -> session/API JSON -> selected candidate UI`.

## Compatibility rule
The independent `target1_audit` already reconstructs the Production Target1 policy. If its `formula_status == MATCH`, it may backfill missing explainability-only fields:
- target1_cap_applied
- target1_cap_price
- structural_target1_price
- structural_target1_basis
- target1_fallback_used

It must never rewrite Target1, Target2, Entry, Stop, RR, Strategy, Candidate state, or Rank.

Frontend may read the same audit metadata as a compatibility fallback for already-restored/partial Scanner payloads. It must not infer cap state from `rr1 == 1.5`.

## Version
Scanner decision version remains `0.21.3.6`.
