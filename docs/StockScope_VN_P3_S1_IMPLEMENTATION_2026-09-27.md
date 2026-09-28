# StockScope VN-P3-S1 Implementation Checkpoint

Date: 2026-09-27  
Stage: VN-P3-S1 — 기존 관리계획 위의 보유 판단 지원  
Branch: `feature/ux-redesign-1`  
Implementation base: `ad017f384eb79beeee1f607a60a3b0a15067afcf`

## 1. Purpose implemented

VN-P3-S1 adds a persisted Holdings decision-support layer above the existing immutable ledger, latest confirmed-EOD analysis, and explicitly applied management plan.

The implemented flow is:

```
current position / ledger state
+ latest confirmed-EOD valuation
+ latest analysis revision
+ currently applied management plan
+ Horizon context
        ↓
persisted holding decision
        ↓
user review / acknowledgement
        ↓
optional explicit plan application
```

A decision is not an order, a trade event, or a position lifecycle state.

## 2. Preserved boundaries

Unchanged:

- `holding_position` ownership and quantity/average-price semantics
- `holding_position_event` BUY/SELL/CORRECTION/observation semantics
- KIS balance observation does not infer executed trades
- historical analysis revisions
- existing management-plan version history
- real broker orders remain absent
- Realtime quote remains a projection/distance input only
- TRACK.1 and `backend/app/tracking/*`
- Scanner ranking/scoring core
- Strategy/Risk calculations
- P2 prospective/feedback stores
- unresolved numeric Horizon policy
- Recovery automation

A new analysis still does not replace an active plan automatically.

## 3. Decision policy

Versions:

- storage: `VN_P3_S1_HOLDING_DECISION_STORAGE_V1`
- decision policy: `VN_P3_S1_HOLDING_DECISION_POLICY_V1`
- plan context: `VN_P3_S1_PLAN_CONTEXT_V1`

Supported decision actions:

- HOLD
- ADD
- REDUCE
- TAKE_PROFIT
- STOP
- EXIT

Decision statuses:

- ACTIONABLE
- REVIEW_REQUIRED
- DEFERRED
- INSUFFICIENT_DATA
- CONFLICT

`STALE` is an effective read status derived from a frozen decision versus current state; the immutable original decision row is not rewritten.

### Action rules in P3-S1

No new return/probability threshold was invented.

Existing applied-plan boundaries are reused:

- WITHIN_PLAN -> HOLD can be reviewed
- STOP_BREACHED -> STOP is the primary actionable review
- TARGET1_REACHED / TARGET2_REACHED -> TAKE_PROFIT becomes the primary review
- REDUCE can be shown as a manual review option, but no percentage/quantity is generated
- EXIT can be shown as a user review option, but no automatic full sale occurs
- ADD is always BLOCKED in P3-S1 because a validated averaging/addition policy is not yet defined

Missing data is not silently converted to HOLD.

## 4. Persistent storage

Explicit migration:

```powershell
python tools/data/migrate_holdings_decision_vnp3s1.py
```

New Holdings DB tables:

- `holding_decision_schema_meta`
- `holding_decision_record`
- `holding_decision_resolution`
- `holding_management_plan_context_vnp3s1`

### holding_decision_record

A decision freezes:

- Position ID/status/quantity/average price
- source Analysis Revision
- source active Plan ID/version
- confirmed EOD market date/price/source
- Horizon intent/policy version
- decision status/primary action
- evidence/options/limitations
- deterministic input fingerprint
- creation time

Decision rows are append-only.

If an explicit re-evaluation sees the same decision fingerprint, it reuses the existing decision instead of creating duplicate history.

### holding_decision_resolution

User review outcomes are append-only and separate from the decision.

Supported resolution types:

- KEEP_CURRENT_PLAN
- APPLY_NEW_PLAN
- ACKNOWLEDGED
- DEFERRED

### holding_management_plan_context_vnp3s1

A plan explicitly applied through P3-S1 stores its source Decision and selected action.

Unresolved numeric policy remains null:

- `review_cycle_trading_days = NULL`
- `time_stop_trading_days = NULL`

No arbitrary SHORT/MEDIUM/LONG duration values are generated.

## 5. Explicit evaluation vs reads

Read route:

`GET /api/holdings/stocks/{stock_id}/decision-support`

only reads stored decisions and computes whether they are stale. It does not create a Decision, run Scanner, prepare Market data, or migrate schema.

Explicit evaluation:

`POST /api/holdings/positions/{position_id}/decisions/evaluate`

creates/reuses a frozen decision from already stored Holdings/analysis/EOD state.

Migration is never hidden behind GET or API import.

Before migration, existing Holdings features remain usable and only P3-S1 returns:

`HOLD_DECISION_MIGRATION_REQUIRED`

## 6. Stale protection

A decision becomes stale when its frozen context differs from current state, including:

- Position status changed
- quantity changed
- average price changed
- latest Analysis Revision changed
- active Plan ID/version changed
- confirmed-EOD valuation date/price changed

A stale Decision cannot be resolved or used to apply a new Plan.

The UI asks the user to create a fresh decision instead.

## 7. Explicit Plan application

New path:

`POST /api/holdings/decisions/{decision_id}/apply-plan`

The existing compatibility route:

`POST /api/holdings/positions/{position_id}/plans/apply`

is retained, but the normal Holdings UI no longer exposes a direct plan-apply bypass.

The P3-S1 path:

1. validates Decision state
2. rechecks Position state inside the Holdings transaction
3. rechecks current Analysis Revision
4. rechecks active Plan ID/version
5. calls the same shared management-plan transaction helper used by the legacy route
6. preserves Horizon activation gate
7. preserves stop-loosening protection
8. creates the new Plan version
9. writes P3-S1 plan context
10. writes APPLY_NEW_PLAN resolution
11. commits together in the Holdings DB transaction

It does not create BUY/SELL events or change Position quantity/average price.

## 8. Existing management safety reused

`HoldingManagementService.apply_analysis_plan()` was refactored to call a shared transaction-scoped helper:

`_apply_analysis_plan_in_conn(...)`

The validation semantics are preserved, including:

- Position must exist and be OPEN
- Analysis Revision must exist and belong to the same stock
- future Analysis Revision is rejected
- Horizon must be activatable
- stop/target values must be valid
- active Plan versioning/supersession remains unchanged
- a lower stop than the current active Plan remains blocked by:
  `HOLD_PLAN_STOP_LOOSENING_BLOCKED`

The Decision layer cannot bypass stop loosening by selecting HOLD, changing Horizon, or using a different UI path.

## 9. Realtime boundary

P3-S1 official decisions use confirmed EOD, not live quote.

Realtime/KIS quote still provides:

- current valuation projection
- stop/target distance

A quote update does not modify:

- Decision
- Position ledger
- Analysis Revision
- applied Plan

Realtime Watch and durable alert lifecycle remain P4 scope.

## 10. Account exposure limitation

P3-S1 does not claim whole-net-worth concentration when StockScope cannot see:

- cash
- another broker/account
- unregistered assets

Decision limitations explicitly state that account exposure is partial.

This incomplete exposure is another reason ADD is not activated.

## 11. Frontend

A separate `HoldingDecisionPanel.tsx` is inserted into the held-position hierarchy before the detailed management-plan block.

Default user flow:

- current decision headline
- concise explanation
- confirmed EOD basis
- available/review/blocked action choices
- explicit “현재 판단 업데이트”
- optional acknowledgement/keep-plan record
- optional “새 분석 계획 적용”

Internal identifiers/fingerprint details are kept under a collapsed evidence/limitations section.

The old direct `이 계획 적용` Workspace button was removed from the default path. Compatible backend API remains available for existing integrations/tests, but normal UI mutations pass through persisted decision review.

ADD is displayed as blocked rather than as a recommendation.

Responsive rules were added for narrow widths without introducing generic card-heavy layout.

## 12. API

Read:

- `GET /stocks/{stock_id}/decision-support`
- `GET /decisions/{decision_id}`

Explicit commands:

- `POST /positions/{position_id}/decisions/evaluate`
- `POST /decisions/{decision_id}/resolve`
- `POST /decisions/{decision_id}/apply-plan`

No order endpoints were added.

## 13. DATA.1 / backup and restore

The optional decision family is validated by `validate_holdings_db`.

Validation includes:

- all-or-none P3-S1 table family
- schema version
- normal SQLite integrity/FK validation
- APPLY_NEW_PLAN resolution must reference a resulting Plan
- Review Cycle/Time Stop numeric fields must remain null in P3-S1

Backup manifest extension:

`holding_decision_v1`

records presence, table set, schema version, and restorable state.

Because the state lives in `holdings.db`, normal Holdings restore restores these rows together with the ledger.

Automated roundtrip verifies:

- Decision
- Resolution
- Plan Context
- null unresolved numeric Horizon fields

after backup -> restore.

## 14. Automated regression evidence

At code checkpoint `17f0dd16ba9d18eeb23d254fe58882cc48e367bf`:

- Frontend / Node 22: PASS
- Backend / Python 3.11: 1116 passed
- Backend / Python 3.14: 1116 passed
- existing Starlette anyio deprecation warning: 1 per Python version

Coverage added for:

- explicit/idempotent migration
- incompatible migration rollback
- no historical Decision backfill
- GET does not create Decision
- missing migration does not mutate Holdings
- STOP/HOLD/TARGET state mapping
- ADD policy block
- same-input Decision reuse
- quantity/average/analysis/plan stale protection
- Decision apply preserves ledger quantity/average/event count
- Plan v1 -> v2 versioning and previous-plan reference
- stop-loosening cannot be bypassed
- append-only Decision/Resolution
- API explicit read/evaluate/apply boundary
- P3-S1 backup/restore roundtrip
- updated existing UX/realtime contracts to reflect the Decision gate

## 15. Diff audit

Compared with P3-S1 implementation base `ad017f384eb79beeee1f607a60a3b0a15067afcf`:

Changed domains are limited to:

- Holdings backend/API
- Holdings frontend/API/CSS
- DATA.1 tools
- related tests/docs

No changes were made to:

- `backend/app/tracking/*`
- Scanner calculation/ranking core
- Strategy calculation core
- Risk calculation core
- real-order routes

## 16. Current completion boundary

Implemented / automated:

- P3-S1 Decision storage
- explicit evaluation
- action/limitation contract
- stale detection
- append-only resolution
- explicit Plan apply through Decision
- legacy Plan safety reuse
- UI Decision hierarchy
- migration
- backup/restore/integrity
- automated regression

Still requires user-runtime evidence:

- user local P3-S1 migration
- browser UAT in `내 종목 관리`
- explicit stale-decision browser scenario if feasible

Still out of scope / blocked:

- automatic ADD policy
- averaging-down amount/ratio
- automatic REDUCE percentage
- automatic Recovery entry/exit
- arbitrary Horizon Review Cycle / Time Stop
- Realtime Watch alerts
- Strategy automatic rotation
- real broker orders

Implementation completion does not mean investment-performance improvement is proven.
