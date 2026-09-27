# StockScope VN-P2-S2 Implementation Checkpoint

Date: 2026-09-27  
Stage: VN-P2-S2 — 실제 추천 보존과 시간 분리 평가  
Branch: `feature/ux-redesign-1`

## 1. Implemented purpose

P2-S2 preserves completed Production Scanner recommendations before a user chooses Tracking rows, then evaluates those immutable recommendation samples later with local confirmed EOD data under a frozen time-split protocol.

This stage provides evaluation infrastructure. It does not claim strategy superiority and does not activate strategy promotion, demotion, or adaptive rotation.

## 2. Preserved boundaries

Unchanged:

- `backend/app/tracking/*` and TRACK.1 schema/service/row-action semantics
- Scanner ranking/scoring core
- Strategy score formulas
- Risk gates
- completed VAL.1 / VAL.2 rows
- Holdings ledger and applied plans
- Production strategy selection
- real broker order boundary
- unresolved Horizon numeric policy

Tracking registration is not a prospective-sample selection mechanism. A recommendation can be preserved for evaluation even if the user never starts Tracking it.

## 3. Prospective capture

Versions:

- storage: `VN_P2_S2_PROSPECTIVE_STORAGE_V1`
- capture: `VN_P2_S2_CAPTURE_V1`

A Scanner job attempts to create a PENDING capture after the normal Scanner/Horizon gate. Missing P2-S2 migration does not fail Scanner; capture reports `NOT_READY`.

After the Scanner result is committed in memory, P2-S2 freezes:

- Scanner version / baseline when available
- market scope
- requested/actual data date
- candidate limit
- input fingerprint
- Horizon context
- candidate list returned by that completed run
- candidate rank / strategy / decision state / action
- complete candidate snapshot and hash
- result/source snapshot hashes

The stable source identity includes the Scanner/input/result context rather than relying only on the process-memory job ID.

The same completed Scanner result exposed through another job is not counted twice. One capture is canonical `COMPLETE`; a repeated identical source becomes `DUPLICATE`.

`partial_data=true` becomes `PARTIAL`. Its snapshot is retained for audit, but PARTIAL rows are not included in normal prospective evaluation samples.

No historical Scanner result is backfilled as prospective evidence.

## 4. Capture lifecycle and restart behavior

Stored capture states include:

- PENDING
- COMPLETE
- DUPLICATE
- PARTIAL
- FAILED
- CANCELLED
- INTERRUPTED

Terminal capture snapshots are immutable.

On backend startup, a capture left PENDING by a previous process is marked INTERRUPTED. Reads do not perform this mutation; it is an explicit lifecycle recovery action in application startup.

Capture-storage failure is separated from Scanner success. Evaluation persistence must not hide an otherwise valid Scanner result.

## 5. Time-split evaluation protocol

Version:

`VN_P2_S2_PROTOCOL_V1`

A protocol is immutable after creation. It freezes:

- market scope
- optional strategy scope
- Development start/end
- Holdout start/end
- observation windows: existing D+5 / D+10 / D+20 definition
- purge window
- execution mode
- max holding days
- execution policy version
- Production exit-policy token
- cost/slippage assumptions

Development and Holdout periods are both required.

The implementation does not invent the unresolved Q7 values for:

- minimum sample
- recent/long-term production periods
- strategy promotion threshold
- strategy demotion threshold

The current 20-day observation definition is reused only as an evaluation window; it is not reinterpreted as SHORT Horizon.

If an evaluation condition is changed after inspecting results, a new immutable protocol must be created.

## 6. Leakage prevention

Evaluation reads only the local Market Store.

For each sample:

- the Scanner signal is fixed at D
- signal reconstruction uses rows only through D
- D+1 and later rows are used only for outcome observation/execution
- the existing signal audit must not report future-data use
- stored strategy/action/candidate-state is compared to reconstructed D state before virtual execution
- a mismatch becomes failed evidence instead of being silently accepted

A Development signal whose future evaluation window crosses the Holdout boundary is marked:

`PURGED / HOLDOUT_BOUNDARY_OVERLAP`

and is not mixed into the normal evaluation denominator.

## 7. Observation and virtual execution

Candidate observation preserves:

- D+5 / D+10 / D+20 return
- MFE / MAE
- entry/stop/target touch observation

Touch observation is not treated as a trade.

For eligible ENTRY_CANDIDATE evidence, P2-S2 reuses the existing Production execution simulator rather than implementing another exit engine.

Possible virtual execution states remain distinct, including:

- NOT_EXECUTED
- RISK_PLAN_BLOCKED
- CLOSED
- CENSORED
- FAILED / NOT_EVALUATED where applicable

CENSORED mark return is reported separately and is never a realized return or forced 0%.

The Production exit-policy token is frozen in the protocol. A later Production policy change blocks reuse of that protocol for execution evaluation and requires a new protocol.

## 8. Persistent evaluation lifecycle

Version:

`VN_P2_S2_EVALUATION_V1`

Evaluation-run state is stored in Simulation DB, including:

- source counts
- Development / Holdout / Purged counts
- mature / immature / excluded / failed counts
- processed count
- cancellation request
- restart count
- failure/interruption state

Cancellation is persistent and checked between samples.

A RUNNING evaluation found during backend startup becomes INTERRUPTED. Because no safe per-sample result checkpoint is committed before final report creation, interrupted/failed evaluation is restarted from its frozen sources rather than falsely described as a resume.

A user-cancelled run is not reused; a new evaluation run is required.

## 9. Reports

Version:

`VN_P2_S2_REPORT_V1`

A completed report keeps observation and virtual execution separate and includes:

- total source captures / samples
- Development / Holdout / Purged counts
- mature / immature / excluded / failed counts
- market and strategy sample distribution
- D+5 / D+10 / D+20 observation
- realized virtual execution return
- CENSORED mark-return evidence separately
- strategy breakdown without winner/ranking claims

Every report explicitly keeps:

- `minimum_sample_policy_defined = false`
- `performance_conclusion_allowed = false`
- `strategy_promotion_allowed = false`
- `adaptive_rotation_enabled = false`

Possible evidence states include `INSUFFICIENT_EVIDENCE` and `SAMPLE_SIZE_POLICY_UNDEFINED`.

## 10. Storage and migration

P2-S2 adds only Simulation DB tables:

- `prospective_schema_meta`
- `prospective_capture_run`
- `prospective_recommendation_sample`
- `prospective_evaluation_protocol`
- `prospective_evaluation_run`
- `prospective_evaluation_unit`
- `prospective_evaluation_report`

Tracking DB is unchanged.

Explicit migration:

```powershell
python tools/data/migrate_prospective_vnp2s2.py
```

Properties:

- never hidden in GET/API import
- repeatable
- transactional
- incompatible-schema validation and rollback
- FK/integrity validation
- no historical prospective backfill
- existing P2-S1/VAL.1/VAL.2 storage retained

This implementation session did not execute the P2-S2 migration on the user's runtime DB.

## 11. API

Base:

`/api/simulation/prospective`

Read-only state endpoints:

- `GET /status`
- `GET /captures`
- `GET /protocols`
- `GET /evaluation-runs`
- `GET /evaluation-runs/{id}`

Explicit actions:

- `POST /protocols`
- `POST /evaluation-runs`
- `POST /evaluation-runs/{id}/execute`
- `POST /evaluation-runs/{id}/cancel`

GET requests do not run Scanner, download Market data, migrate DBs, or start evaluation.

## 12. Frontend

The primary Validation workspace now shows a user-facing prospective section first:

- recommendation recording count
- collection start/latest date
- successful collection count
- partial/failed/interrupted collection count
- current evidence state
- mature / still-observing / excluded counts
- D+5 / D+10 / D+20 observation when available
- realized virtual execution separately
- explicit statement that strategy auto-change is disabled

The time-split protocol configuration is under a details section rather than the main browsing path.

The P2-S1 raw source/cohort/ID UI is retained for audit/UAT but moved under:

`상세 평가 근거 · 고급`

so internal identifiers are no longer the primary user experience.

## 13. DATA.1

Simulation validation recognizes the prospective table family.

Backup manifest extension:

`prospective_evaluation_v1`

records:

- schema version
- table presence
- complete restorable state
- included prospective tables

Restore reports whether the prospective store was restored.

Roundtrip regression covers capture, sample, protocol, evaluation unit, and report persistence.

Market Store remains a separate input owner and is not duplicated into prospective tables.

## 14. Regression evidence

Automated tests cover:

- migration idempotency and no historical backfill
- incompatible schema rollback
- prospective capture independent from Tracking
- same-result deduplication
- missing migration does not break Scanner
- PENDING capture restart -> INTERRUPTED
- RUNNING evaluation restart -> INTERRUPTED
- restart count
- explicit Development/Holdout requirement
- holding/observation overlap purge
- Holdout kept separate
- non-entry candidate not treated as execution
- CENSORED mark return not realized
- persistent evaluation cancellation
- PARTIAL capture excluded from normal evaluation
- same-job finalize retry idempotency
- prospective backup/restore roundtrip

At code checkpoint `93b5a1c3ac15fc64c7f7714dc28181bbc47cdae5` before documentation-only follow-up:

- Frontend / Node 22: PASS
- Backend / Python 3.11: 1097 passed
- Backend / Python 3.14: 1097 passed

## 15. Current completion boundary

Implemented / automated:

- prospective capture contract
- explicit migration
- dedupe/failure/interruption lifecycle
- immutable protocol
- local-only time-split evaluator
- existing Production execution reuse
- cancellation/restart distinction
- report storage
- user-facing minimal UI
- advanced technical evidence UI separation
- backup/restore
- automated regression

Not yet proven/activated:

- user runtime P2-S2 migration
- browser UAT of a post-migration Scanner capture
- real long-term prospective sample maturity
- minimum sample thresholds
- strategy promotion/demotion
- Strategy Pool activation
- Adaptive Rotation

Therefore implementation completion must not be reported as strategy-performance validation or strategy-operation activation.
