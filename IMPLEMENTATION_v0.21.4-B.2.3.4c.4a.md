# StockScope v0.21.4-B.2.3.4c.4a — Implementation Notes

## Implemented

- Replaced c.4's broad RS numeric candidate selection with an AST-scoped Breakout definition inspector.
- The audit now reads only `_breakout()` tuples whose label is exactly `20일 업종 대비 상대강도 양호`.
- Fail-fast requires exactly two equivalent predicates with weights `[4, 8]`; otherwise the audit aborts instead of producing misleading results.
- Added two independent audit-only variants:
  - `RS_KEEP_4`: keep weight 4, remove the duplicated weight 8 contribution.
  - `RS_KEEP_8`: keep weight 8, remove the duplicated weight 4 contribution.
- The removed contribution is subtracted only when the duplicated condition actually passed. Failed duplicated conditions only reduce the condition count; score is unchanged.
- Dedup changes are propagated through strategy re-sorting/reselection, current readiness/Risk evaluation, Quick18 selection, final ranking, and Top5.
- Added runtime classification for sector-RS availability: `SECTOR_AVAILABLE`, `MARKET_FALLBACK`, `BOTH_MISSING`.
- Added per-variant counts for Breakout score changes, selected-strategy changes, Breakout→other transitions, Quick18 changes, Top5 changes, state/Risk changes, and forward metrics.
- Paired Top5 output now records removed weight, old/new strategies, return/R deltas, and event status for 5D/10D/20D.
- MA120 counterfactual logic remains unchanged from c.4.
- Inspect mode always remains `INCONCLUSIVE`; it is a hotfix/sanity stage, not a production policy verdict.
- Full mode exposes independent `RS_KEEP_4` and `RS_KEEP_8` impacts plus a separate RS policy verdict.

## Safety / invariant

- `backend/app/strategy/engine.py` is not included in this overlay and is not modified.
- No Production strategy, threshold, weight, ranking, Quick18, Market160, Risk, Target, or Historical Evidence policy is changed.
- The old broad `condition_weight_candidates` report is retained only as a diagnostic field; c.4a never uses it to choose the dedup weight.

## Validation performed in overlay environment

- Python compile: PASS for the modified audit module, runner, and test file.
- New c.4a integrity tests: **10 passed**.
- Combined pruning / Top3 / pre-pool / integrity audit regression + scanner determinism + candidate priority: **42 passed**.
- Output smoke: PASS; JSON/CSV/pairs/Markdown all generated and Markdown reported `Detected duplicate weights: [4.0, 8.0]`, `RS_KEEP_4`, and `RS_KEEP_8` separately.
- AST fixture containing unrelated numeric value `1.0` still detected only `[4.0, 8.0]` from the exact Breakout tuples.
- Fail-fast fixture with `[1,4,8]` correctly aborted.
- PASS-only score removal, original-evaluation immutability, strategy reselection, Quick-pool propagation, Top5 propagation, MA120 regression, and no-lookahead selection fixtures passed.

## Not validated here

- The user's actual `market_history.db` is not available in this environment, so the real 10-date and 80-date StockScope integration runs were not executed here.
- The user's real repository will be source-inspected at runtime. If the Breakout definition is no longer exactly two equivalent `[4,8]` conditions, c.4a intentionally aborts and asks for re-audit rather than guessing.

## Recommended next run

First run only the 10-date inspect hotfix:

```powershell
python tools\run_scanner_strategy_integrity_audit.py --mode inspect --sample-size 10 --min-date-gap 3
```

Expected source line in the terminal/summary:

```text
Detected duplicate weights: [4.0, 8.0]
```

Only after that result is confirmed should the 80-date full audit be run.
