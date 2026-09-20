# WORKSPEC v0.21.4-B.2.3.4c.4f.3 — Sector RS Audit Coverage Wiring

## Goal
Connect c.4f prepared Sector RS inputs to the Strategy Integrity Audit without authorizing Production use.

## Scope
- Opt-in live audit prefetch using current OpenDART company metadata + historical KRX sector EOD.
- Pass prepared sector inputs into BacktestEngine snapshots.
- Read audit-only sector value/context from `sector_input_audit`.
- Report industry mapping / benchmark / history / 20D coverage / temporal status / unavailable reasons.
- Reuse company metadata and KRX index-day responses across fixed multi-date audits.
- Preserve default offline Strategy Integrity Audit behavior when the live flag is absent.

## Temporal policy
Current OpenDART industry metadata is `STATIC_CURRENT`. It may be used to measure audit coverage only.
It MUST NOT populate Production `StrategyInput.relative_strength_sector_pct` until a point-in-time mapping source exists.

## Forbidden changes
- Breakout 6+4+8 weights
- Sector→market fallback
- Ranking / Quick18 / Quick36 / Market160
- Risk / Entry / Stop / Target / Exit
- MA120 behavior

## Gate
Run fixed c4c 10 dates with `--sector-rs-audit-live` only after unit/regression tests pass.
