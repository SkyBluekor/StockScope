# StockScope VN-P2-S1 Implementation Checkpoint

Date: 2026-09-27  
Stage: VN-P2-S1 — 평가 근거 어댑터와 비교 cohort  
Branch: `feature/ux-redesign-1`

## 1. Scope

This checkpoint records the implemented P2-S1 contract on top of the reviewed vNext architecture and roadmap.

P2-S1 does **not** introduce a new execution engine. It reuses existing results and preserves their original meanings:

- Tracking observation
- Historical Validation (VAL.1) D+1 observation
- Execution Validation (VAL.2) virtual execution
- completed in-memory Backtest jobs

The Feedback layer is responsible for evidence normalization, comparison compatibility, cohort snapshotting, report versioning, source verification, and user-facing comparison.

## 2. Frozen boundaries preserved

The implementation does not modify `backend/app/tracking/*`.

The following remain unchanged:

- TRACK.1 DB schema and service semantics
- Tracking register / merge / close / delete behavior
- Tracking performance meaning
- Tracking price touched != virtual execution
- completed VAL.1 / VAL.2 source rows
- Scanner / Strategy / Risk calculations
- actual Holdings ledger semantics
- real broker order boundary

Manual-only Tracking rows can be inspected as evidence but are excluded from Scanner-performance evidence.

## 3. Evidence contract

Version:

`VN_P2_S1_EVIDENCE_ADAPTER_V1`

Every evidence row retains:

- source type / owner / source ID / source item ID
- source hash
- durable vs ephemeral source status
- observation vs virtual-execution vs backtest origin
- market / ticker / signal date
- strategy / decision status
- Scanner version / baseline
- Horizon intent / Horizon policy version
- metric definition
- execution / exit policy version
- cost assumptions when available
- maturity state
- inclusion / exclusion state and reason
- metric payload
- source observed timestamp
- comparison dimensions

Comparison compatibility includes, when applicable:

- origin and metric definition
- market and market scope
- strategy
- Scanner version / baseline
- Horizon
- execution / exit policy
- fee / tax / slippage
- selector date range
- source evaluation period
- round-trip cost
- max holding days
- market-data cutoff
- selection method
- evaluation window

Different comparison keys are never merged into one performance aggregate.

## 4. Source adapters

### Tracking

Tracking is opened with SQLite read-only mode and `PRAGMA query_only=ON`.

- Scanner-provenance rows: eligible
- Manual-only rows: `EXCLUDED / MANUAL_ONLY`
- D+5 / D+10 / D+20 observation retained
- MFE / MAE retained
- entry/stop/target touched retained
- reached price is explicitly not treated as execution
- ACTIVE performance changes change the source hash and make prior derived reports stale

### VAL.1

Reads completed stored Scanner replay candidates and existing candidate outcomes.

- D+5 / D+10 / D+20 remain observation metrics
- MFE / MAE remain observation metrics
- immature candidates remain immature
- no replay or Market Store calculation is hidden in Feedback reads

### VAL.2

Reads stored execution outcomes.

- CLOSED -> realized virtual execution sample
- CENSORED -> censored sample
- OPEN -> immature
- NOT_EXECUTED / NO_ENTRY_DATA / RISK_PLAN_BLOCKED remain non-executed
- CENSORED is never converted to realized P/L or 0%
- execution policy, exit-policy token and costs remain comparison dimensions

### Backtest

Current Backtest jobs are process-memory state, so P2-S1 exposes them as:

`durability = EPHEMERAL`

A missing job after backend restart is reported as missing source. P2-S1 does not pretend current Backtest jobs are durable artifacts.

## 5. Feedback storage

Version:

`VN_P2_S1_FEEDBACK_STORAGE_V1`

New Simulation DB tables:

- `feedback_schema_meta`
- `feedback_source_ref`
- `feedback_cohort`
- `feedback_cohort_source`
- `feedback_cohort_member`
- `feedback_report`

Tracking DB is not extended.

Source references and reports are immutable snapshots. A new calculation creates a new report sequence rather than rewriting an old report.

Client request IDs provide idempotency for cohort/report creation.

Duplicate source selectors may remain visible as selector records, while identical source evidence is counted only once as a cohort member.

## 6. Explicit migration

Migration is never hidden inside API import, GET, or normal application reads.

Command:

```powershell
python tools/data/migrate_feedback_vnp2s1.py
```

The migration:

- requires existing Validation / Execution source tables
- uses an explicit transaction
- validates existing table columns before dependent indexes/triggers
- checks foreign keys
- is repeatable
- rolls back newly created objects on incompatible-schema failure

No user runtime migration was executed by this implementation session.

## 7. Cohort and report rules

Cohort version:

`VN_P2_S1_COHORT_V1`

Report version:

`VN_P2_S1_REPORT_V1`

A report shows:

- selector count
- source read failures
- total evidence members
- included / excluded counts
- comparison-group count
- mature / immature / censored / non-executed distribution
- observation metrics only inside compatible observation groups
- realized virtual-return metrics only for realized execution/backtest groups
- censored mark return separately
- source verification

Minimum-sample thresholds are still unresolved in the vNext design.

Therefore P2-S1 explicitly reports:

- `minimum_sample_policy_defined = false`
- `performance_conclusion_allowed = false`
- no strategy promotion / demotion conclusion

If metric evidence is unavailable the report uses `INSUFFICIENT_EVIDENCE`. Otherwise it uses `SAMPLE_SIZE_POLICY_UNDEFINED` until a later approved minimum-sample policy exists.

## 8. Source lifecycle

Reports retain the source hashes captured at creation.

When the current source is checked later:

- same hash -> MATCH
- changed source -> SOURCE_CHANGED
- deleted / unavailable source -> SOURCE_MISSING

A prior report summary is not silently rewritten. Its effective status becomes `SOURCE_INVALID` when its source evidence can no longer be verified.

This also covers ACTIVE Tracking observations whose performance naturally changes over time.

## 9. API

Base:

`/api/simulation/feedback`

Endpoints:

- `GET /evidence`
- `POST /cohorts`
- `GET /cohorts`
- `GET /cohorts/{cohort_id}`
- `POST /cohorts/{cohort_id}/reports`
- `GET /reports/{report_id}`

Missing explicit migration is surfaced as `FEEDBACK_MIGRATION_REQUIRED`; the API does not auto-create Feedback schema.

## 10. Frontend

Simulation saved-workspace now has a separate Feedback / Validation area.

It can:

- add the currently selected completed VAL.1 source
- add all Scanner-provenance Tracking evidence
- add explicit VAL.1 / VAL.2 / Tracking / Backtest source IDs
- create a cohort explicitly
- show source errors and exclusion counts
- create a new immutable report explicitly
- show evidence state, group count, sample count and source verification
- show compatible groups separately by origin / market / strategy / Horizon / policy
- show 20D observation separately from realized virtual return
- show CENSORED count separately

The UI intentionally does not rank strategies or claim a winner.

The layout is typography / table / divider based and avoids repeated generic card tiles.

## 11. Backup and restore

DATA.1 now recognizes the Feedback table family inside Simulation DB.

Backup manifest extension:

`feedback_v1`

It records:

- schema version
- whether Feedback storage is present
- Feedback tables included
- whether the complete Feedback storage is restorable

Restore reports whether Feedback storage was restored.

Tracking remains a separate database and remains a read-only evidence owner from the Feedback layer.

## 12. Regression coverage added

P2-S1 tests cover:

- Tracking adapter read-only behavior
- Manual-only exclusion
- CENSORED separation from realized return
- incompatible execution policies separated
- evaluation period and cost assumptions separated
- source deletion invalidates derived report without rewriting it
- ACTIVE Tracking source change detection
- duplicate selector deduplication
- selector date validation
- cohort/report idempotency
- explicit migration requirement
- migration repeatability
- migration rollback on incompatible schema
- Feedback backup / restore roundtrip

Full backend suite and frontend build remain the final automated gate.

## 13. Remaining limits

The following are **not** completed by P2-S1:

- actual browser UAT
- user-machine/runtime migration execution
- minimum sample threshold
- strategy promotion / demotion threshold
- adaptive strategy rotation
- prospective production recommendation capture
- durable general Backtest result store
- P2-S2+ evaluation protocol expansion

P2-S1 is an evidence and comparison foundation only. It does not authorize production strategy changes.
